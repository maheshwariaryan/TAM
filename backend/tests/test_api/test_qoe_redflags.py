"""
Full HTTP flow tests for the QoE and Red Flag APIs.

Tests the end-to-end path:
  POST /deals → upload sample_gl.csv
  → /process (ingestion, financial_builder, qoe_engine, redflag_detector)
  → poll status → assert GET /qoe and GET /redflags responses

All tests use USE_MOCK_LLM=true (the default), so no Anthropic API key is required.
"""

import time
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURES = Path(__file__).parent.parent / "fixtures"

STAGE_ORDER = ["ingestion", "financial_builder", "qoe_engine", "redflag_detector"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _create_deal(name: str) -> str:
    resp = client.post("/api/v1/deals", json={
        "company_name": name,
        "deal_name": f"{name} — Step 4 Test",
        "currency": "USD",
    })
    assert resp.status_code == 201
    return resp.json()["deal_id"]


def _upload_gl(deal_id: str) -> None:
    with open(FIXTURES / "sample_gl.csv", "rb") as f:
        resp = client.post(
            f"/api/v1/deals/{deal_id}/upload",
            files={"files": ("sample_gl.csv", f, "text/csv")},
        )
    assert resp.status_code == 200


def _run_stage(deal_id: str, *stages: str) -> None:
    resp = client.post(
        f"/api/v1/deals/{deal_id}/process",
        json={"stages": list(stages)},
    )
    assert resp.status_code == 200


def _poll_stage(deal_id: str, stage: str, timeout: int = 90) -> dict:
    for _ in range(timeout * 2):
        resp = client.get(f"/api/v1/deals/{deal_id}/status")
        assert resp.status_code == 200
        deal = resp.json()
        status = deal["stages"].get(stage)
        if status == "complete":
            return deal
        if status == "failed":
            pytest.fail(f"Stage '{stage}' failed: {deal.get('error')}")
        time.sleep(0.5)
    pytest.fail(f"Stage '{stage}' timed out after {timeout}s")


@pytest.fixture(scope="module")
def processed_deal() -> dict:
    """
    Create one deal, run all four stages in sequence.
    Module-scoped so every test class shares the same processed deal.
    """
    deal_id = _create_deal("QoE RF Test Co")
    _upload_gl(deal_id)

    for stage in STAGE_ORDER:
        _run_stage(deal_id, stage)
        _poll_stage(deal_id, stage)

    return {"deal_id": deal_id}


# ── QoE endpoint tests ─────────────────────────────────────────────────────────

class TestQoEEndpoint:
    def test_qoe_200(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        resp = client.get(f"/api/v1/deals/{deal_id}/qoe")
        assert resp.status_code == 200

    def test_qoe_adjusted_gt_reported(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        qoe = client.get(f"/api/v1/deals/{deal_id}/qoe").json()
        assert Decimal(qoe["ltm_adjusted"]) > Decimal(qoe["ltm_reported"]), (
            "Adjusted LTM EBITDA must exceed reported (all planted items are add-backs)"
        )

    def test_qoe_at_least_4_adjustments(self, processed_deal):
        """All four planted anomaly types must appear as adjustments."""
        deal_id = processed_deal["deal_id"]
        qoe = client.get(f"/api/v1/deals/{deal_id}/qoe").json()
        rule_ids = {a["rule_triggered"] for a in qoe["adjustments"]}
        expected = {
            "LEGAL_SETTLEMENTS",
            "MA_TRANSACTION_COSTS",
            "RELATED_PARTY_CONSULTING",
            "OWNER_COMP_EXCESS",
        }
        assert expected.issubset(rule_ids), f"Missing adjustments: {expected - rule_ids}"

    def test_qoe_waterfall_base_plus_bars_equals_result(self, processed_deal):
        """Waterfall: base + sum(bars) == result — the Big 4 bridge identity."""
        deal_id = processed_deal["deal_id"]
        qoe = client.get(f"/api/v1/deals/{deal_id}/qoe").json()
        waterfall = qoe["waterfall"]

        base = Decimal(next(w["amount"] for w in waterfall if w["type"] == "base"))
        bars = sum(
            Decimal(w["amount"])
            for w in waterfall
            if w["type"] in ("addback", "deduction")
        )
        result = Decimal(next(w["amount"] for w in waterfall if w["type"] == "result"))

        assert abs(base + bars - result) < Decimal("0.01"), (
            f"Waterfall doesn't balance: {base} + {bars} ≠ {result}"
        )

    def test_qoe_waterfall_at_least_3_items(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        qoe = client.get(f"/api/v1/deals/{deal_id}/qoe").json()
        assert len(qoe["waterfall"]) >= 3, "Expected base + at least 1 bar + result"

    def test_qoe_categories_populated(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        qoe = client.get(f"/api/v1/deals/{deal_id}/qoe").json()
        cats = qoe["categories_adjusted"]
        assert "One-Time / Non-Recurring" in cats
        assert "Owner / Related Party" in cats

    def test_qoe_adjustment_source_drill_through(self, processed_deal):
        """GET /qoe/adjustments/{id}/source returns GL line IDs for audit trail."""
        deal_id = processed_deal["deal_id"]
        qoe = client.get(f"/api/v1/deals/{deal_id}/qoe").json()

        # Pick the legal settlement adjustment (always exactly 1)
        legal = next(
            a for a in qoe["adjustments"] if a["rule_triggered"] == "LEGAL_SETTLEMENTS"
        )
        adj_id = legal["adjustment_id"]

        resp = client.get(f"/api/v1/deals/{deal_id}/qoe/adjustments/{adj_id}/source")
        assert resp.status_code == 200
        body = resp.json()
        assert body["adjustment_id"] == adj_id
        assert body["source_line_count"] > 0
        assert len(body["gl_lines"]) > 0

    def test_qoe_source_404_unknown_adjustment(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        resp = client.get(f"/api/v1/deals/{deal_id}/qoe/adjustments/no-such-id/source")
        assert resp.status_code == 404


# ── Red Flag endpoint tests ────────────────────────────────────────────────────

class TestRedFlagEndpoint:
    def test_redflags_200(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        resp = client.get(f"/api/v1/deals/{deal_id}/redflags")
        assert resp.status_code == 200

    def test_at_least_3_flags(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        rf = client.get(f"/api/v1/deals/{deal_id}/redflags").json()
        assert len(rf["flags"]) >= 3, f"Expected ≥3 flags, got {len(rf['flags'])}"

    def test_has_high_severity_flag(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        rf = client.get(f"/api/v1/deals/{deal_id}/redflags").json()
        high = [f for f in rf["flags"] if f["severity"] == "High"]
        assert len(high) >= 1, "Expected at least one High severity flag"

    def test_related_party_flag_is_high(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        rf = client.get(f"/api/v1/deals/{deal_id}/redflags").json()
        rp = [f for f in rf["flags"] if f["rule_id"] == "RELATED_PARTY_MATERIAL"]
        assert len(rp) == 1
        assert rp[0]["severity"] == "High"

    def test_flags_sorted_high_first(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        rf = client.get(f"/api/v1/deals/{deal_id}/redflags").json()
        order = {"High": 0, "Medium": 1, "Low": 2, "Informational": 3}
        sev = [order[f["severity"]] for f in rf["flags"]]
        assert sev == sorted(sev), "Flags must be sorted High → Medium → Low → Informational"

    def test_severity_filter_high_only(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        rf = client.get(
            f"/api/v1/deals/{deal_id}/redflags", params={"severity": "High"}
        ).json()
        for f in rf["flags"]:
            assert f["severity"] == "High"

    def test_severity_filter_multi(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        rf = client.get(
            f"/api/v1/deals/{deal_id}/redflags", params={"severity": "High,Medium"}
        ).json()
        for f in rf["flags"]:
            assert f["severity"] in ("High", "Medium")

    def test_summary_counts_match_flags(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        rf = client.get(f"/api/v1/deals/{deal_id}/redflags").json()
        flags = rf["flags"]
        s = rf["summary"]
        assert s["high"] == sum(1 for f in flags if f["severity"] == "High")
        assert s["medium"] == sum(1 for f in flags if f["severity"] == "Medium")
        assert s["total"] == len(flags)

    def test_high_medium_flags_have_diligence_questions(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        rf = client.get(f"/api/v1/deals/{deal_id}/redflags").json()
        for f in rf["flags"]:
            if f["severity"] in ("High", "Medium"):
                assert len(f["diligence_questions"]) >= 3, (
                    f"Flag '{f['title']}' ({f['severity']}) missing diligence questions"
                )


class TestRedFlagSummaryEndpoint:
    def test_summary_200(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        resp = client.get(f"/api/v1/deals/{deal_id}/redflags/summary")
        assert resp.status_code == 200

    def test_summary_has_required_keys(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        s = client.get(f"/api/v1/deals/{deal_id}/redflags/summary").json()
        for key in ("high", "medium", "low", "informational", "total"):
            assert key in s, f"Missing key '{key}' in summary"

    def test_summary_total_at_least_3(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        s = client.get(f"/api/v1/deals/{deal_id}/redflags/summary").json()
        assert s["total"] >= 3


# ── 404 before processing ──────────────────────────────────────────────────────

class TestNotReady:
    def test_qoe_404_before_processing(self):
        deal_id = _create_deal("Unprocessed QoE Co")
        _upload_gl(deal_id)
        resp = client.get(f"/api/v1/deals/{deal_id}/qoe")
        assert resp.status_code == 404

    def test_redflags_404_before_processing(self):
        deal_id = _create_deal("Unprocessed RF Co")
        _upload_gl(deal_id)
        resp = client.get(f"/api/v1/deals/{deal_id}/redflags")
        assert resp.status_code == 404

    def test_redflags_summary_404_before_processing(self):
        deal_id = _create_deal("Unprocessed RF Summary Co")
        _upload_gl(deal_id)
        resp = client.get(f"/api/v1/deals/{deal_id}/redflags/summary")
        assert resp.status_code == 404
