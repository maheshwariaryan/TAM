"""API-level ingestion lifecycle tests."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURES = Path(__file__).parent.parent / "fixtures"


def _poll_ingestion(deal_id: str, timeout: int = 30) -> dict:
    for _ in range(timeout):
        resp = client.get(f"/api/v1/deals/{deal_id}/status")
        assert resp.status_code == 200
        deal = resp.json()
        status = deal["stages"].get("ingestion")
        if status == "complete":
            return deal
        if status == "failed":
            pytest.fail(f"Ingestion failed: {deal.get('error')}")
        time.sleep(0.5)
    pytest.fail("Ingestion timed out")


class TestIngestionAPI:
    def test_upload_process_gl_lines(self):
        resp = client.post("/api/v1/deals", json={
            "company_name": "API Test Co",
            "deal_name": "Ingestion API Test",
            "currency": "USD",
        })
        assert resp.status_code == 201
        deal_id = resp.json()["deal_id"]

        with open(FIXTURES / "sample_gl.csv", "rb") as f:
            upload = client.post(
                f"/api/v1/deals/{deal_id}/upload",
                files={"files": ("sample_gl.csv", f, "text/csv")},
            )
        assert upload.status_code == 200

        process = client.post(
            f"/api/v1/deals/{deal_id}/process",
            json={"stages": ["ingestion"]},
        )
        assert process.status_code == 200
        _poll_ingestion(deal_id)

        gl = client.get(f"/api/v1/deals/{deal_id}/gl/lines?page_size=5")
        assert gl.status_code == 200
        assert gl.json()["total"] == 1514

        validation = client.get(f"/api/v1/deals/{deal_id}/gl/validation")
        assert validation.status_code == 200
        assert validation.json()["periods_checked"] == 36

    def test_unbalanced_tb_fails_ingestion(self):
        resp = client.post("/api/v1/deals", json={
            "company_name": "Unbalanced Co",
            "deal_name": "TB Fail Test",
            "currency": "USD",
        })
        deal_id = resp.json()["deal_id"]

        with open(FIXTURES / "unbalanced_trial_balance.csv", "rb") as f:
            client.post(
                f"/api/v1/deals/{deal_id}/upload",
                files={"files": ("unbalanced_trial_balance.csv", f, "text/csv")},
            )

        client.post(f"/api/v1/deals/{deal_id}/process", json={"stages": ["ingestion"]})

        for _ in range(30):
            deal = client.get(f"/api/v1/deals/{deal_id}/status").json()
            if deal["stages"]["ingestion"] == "failed":
                assert "Trial balance does not balance" in (deal.get("error") or "")
                return
            time.sleep(0.5)
        pytest.fail("Expected ingestion to fail for unbalanced TB")

    def test_document_inventory_after_ingestion(self):
        resp = client.post("/api/v1/deals", json={
            "company_name": "Multi Doc Co",
            "deal_name": "Inventory Test",
            "currency": "USD",
        })
        deal_id = resp.json()["deal_id"]

        files_to_upload = [
            ("sample_gl.csv", FIXTURES / "sample_gl.csv"),
            ("sample_ar_aging.csv", FIXTURES / "sample_ar_aging.csv"),
            ("sample_ap_aging.csv", FIXTURES / "sample_ap_aging.csv"),
        ]
        for name, path in files_to_upload:
            with open(path, "rb") as f:
                client.post(
                    f"/api/v1/deals/{deal_id}/upload",
                    files={"files": (name, f, "application/octet-stream")},
                )

        client.post(f"/api/v1/deals/{deal_id}/process", json={"stages": ["ingestion"]})
        _poll_ingestion(deal_id)

        docs = client.get(f"/api/v1/deals/{deal_id}/documents")
        assert docs.status_code == 200
        inventory = docs.json()
        types = {d["document_type"] for d in inventory["documents"]}
        assert "general_ledger" in types
        assert "ar_aging" in types
        assert "ap_aging" in types

    def test_zip_upload_extracts_files(self):
        zip_path = FIXTURES / "data_room.zip"
        if not zip_path.exists():
            pytest.skip("data_room.zip not generated")

        resp = client.post("/api/v1/deals", json={
            "company_name": "ZIP Co",
            "deal_name": "ZIP Test",
            "currency": "USD",
        })
        deal_id = resp.json()["deal_id"]

        with open(zip_path, "rb") as f:
            upload = client.post(
                f"/api/v1/deals/{deal_id}/upload",
                files={"files": ("data_room.zip", f, "application/zip")},
            )
        assert upload.status_code == 200
        assert upload.json()["files_received"] >= 2
