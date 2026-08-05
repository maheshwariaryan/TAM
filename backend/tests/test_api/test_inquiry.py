"""
Inquiry (PBC tracker) CRUD + Decision Queue derivation API tests.
IDOR coverage lives in test_authorization.py (GET in the shared sweep,
mutating endpoints in TestDealScopedMutatingEndpointsBlockNonOwner).
"""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.aging import CrossDocumentValidation, TieOutResult
from app.schemas.documents import DocumentInventory
from app.schemas.redflags import RedFlag, RedFlagReport, RedFlagSummary
from app.storage import file_store
from app.storage.json_io import write_json_encrypted

client = TestClient(app)
from tests.auth_helpers import authenticate as _authenticate  # noqa: E402

_authenticate(client)


def _create_deal(name: str) -> str:
    resp = client.post(
        "/api/v1/deals",
        json={"company_name": name, "deal_name": f"{name} — Inquiry Test", "currency": "USD"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["deal_id"]


class TestInquiryCrud:
    def test_list_empty_when_none_created(self):
        deal_id = _create_deal("Inquiry Empty Co")
        resp = client.get(f"/api/v1/deals/{deal_id}/inquiries")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_then_list_round_trips(self):
        deal_id = _create_deal("Inquiry Create Co")
        create_resp = client.post(
            f"/api/v1/deals/{deal_id}/inquiries",
            json={"request": "Provide AP aging vendor detail", "owner": "Revenue Ops", "due_date": "2026-03-01"},
        )
        assert create_resp.status_code == 201, create_resp.text
        created = create_resp.json()
        assert created["request"] == "Provide AP aging vendor detail"
        assert created["status"] == "Open"
        assert created["deal_id"] == deal_id

        list_resp = client.get(f"/api/v1/deals/{deal_id}/inquiries")
        assert len(list_resp.json()) == 1
        assert list_resp.json()[0]["id"] == created["id"]

    def test_patch_partial_update(self):
        deal_id = _create_deal("Inquiry Patch Co")
        created = client.post(
            f"/api/v1/deals/{deal_id}/inquiries",
            json={"request": "Provide bank statements", "due_date": "2026-03-01"},
        ).json()

        patch_resp = client.patch(
            f"/api/v1/deals/{deal_id}/inquiries/{created['id']}", json={"status": "Resolved"}
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "Resolved"
        assert patch_resp.json()["request"] == "Provide bank statements"

    def test_patch_unknown_id_404s(self):
        deal_id = _create_deal("Inquiry Patch 404 Co")
        resp = client.patch(f"/api/v1/deals/{deal_id}/inquiries/no-such-id", json={"status": "Resolved"})
        assert resp.status_code == 404

    def test_delete_then_list_excludes_it(self):
        deal_id = _create_deal("Inquiry Delete Co")
        created = client.post(
            f"/api/v1/deals/{deal_id}/inquiries", json={"request": "X", "due_date": "2026-03-01"}
        ).json()

        delete_resp = client.delete(f"/api/v1/deals/{deal_id}/inquiries/{created['id']}")
        assert delete_resp.status_code == 204

        assert client.get(f"/api/v1/deals/{deal_id}/inquiries").json() == []

    def test_delete_unknown_id_404s(self):
        deal_id = _create_deal("Inquiry Delete 404 Co")
        resp = client.delete(f"/api/v1/deals/{deal_id}/inquiries/no-such-id")
        assert resp.status_code == 404

    def test_get_404_for_unknown_deal(self):
        resp = client.get("/api/v1/deals/no-such-deal/inquiries")
        assert resp.status_code == 404


class TestDecisionQueueDerivation:
    """Seed a deal with a failing tie-out + a blocking inquiry, assert both appear —
    plus a Ready deal with none of the above shows an empty, non-Blocked queue."""

    def _seed_tie_out_failure(self, deal_id: str) -> None:
        validation = CrossDocumentValidation(
            deal_id=deal_id,
            tie_outs=[
                TieOutResult(
                    name="AR Aging <-> BS AR",
                    expected=Decimal("100000"),
                    observed=Decimal("150000"),
                    difference=Decimal("50000"),
                    variance_pct=50.0,
                    tolerance_pct=0.5,
                    status="Fail",
                    source_documents=["ar_aging.csv"],
                )
            ],
        )
        write_json_encrypted(
            file_store.get_processed_dir(deal_id) / "cross_document_validation.json",
            validation.model_dump(mode="json"),
        )

    def _seed_high_redflag(self, deal_id: str) -> None:
        report = RedFlagReport(
            deal_id=deal_id,
            flags=[
                RedFlag(
                    flag_id="flag-1", deal_id=deal_id, severity="High", category="Revenue Quality",
                    title="Material Related-Party Payments", description="Payments to related parties are material.",
                    source="rule_engine", rule_id="RELATED_PARTY_MATERIAL", affected_periods=["2024-01"],
                )
            ],
            summary=RedFlagSummary(high=1, medium=0, low=0, informational=0, total=1),
        )
        write_json_encrypted(
            file_store.get_processed_dir(deal_id) / "redflag_report.json", report.model_dump(mode="json")
        )

    def _seed_missing_docs(self, deal_id: str) -> None:
        inventory = DocumentInventory(deal_id=deal_id, documents=[], missing_recommended=["ar_aging"])
        write_json_encrypted(
            file_store.get_processed_dir(deal_id) / "document_inventory.json", inventory.model_dump(mode="json")
        )

    def test_empty_deal_is_ready_with_no_items(self):
        deal_id = _create_deal("Decision Queue Ready Co")
        resp = client.get(f"/api/v1/deals/{deal_id}/decision-queue")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["readiness"] == "Ready"

    def test_tie_out_failure_and_blocking_inquiry_both_appear_and_block_readiness(self):
        deal_id = _create_deal("Decision Queue Blocked Co")
        self._seed_tie_out_failure(deal_id)
        client.post(
            f"/api/v1/deals/{deal_id}/inquiries",
            json={"request": "Explain revenue pull-forward", "owner": "Revenue Ops",
                  "due_date": "2026-03-01", "blocking": True},
        )

        resp = client.get(f"/api/v1/deals/{deal_id}/decision-queue")
        assert resp.status_code == 200
        body = resp.json()
        assert body["readiness"] == "Blocked"

        source_tabs = {item["source_tab"] for item in body["items"]}
        assert "risk-assessment" in source_tabs
        assert "inquiry" in source_tabs
        tieout_items = [i for i in body["items"] if i["source_tab"] == "risk-assessment"]
        assert any("AR Aging" in i["source_label"] for i in tieout_items)
        assert all(i["blocking"] for i in body["items"])

    def test_high_redflag_appears_and_blocks_readiness(self):
        deal_id = _create_deal("Decision Queue Redflag Co")
        self._seed_high_redflag(deal_id)

        resp = client.get(f"/api/v1/deals/{deal_id}/decision-queue")
        body = resp.json()
        assert body["readiness"] == "Blocked"
        assert any(i["source_id"] == "flag-1" for i in body["items"])

    def test_missing_docs_appear_but_do_not_block_readiness_alone(self):
        deal_id = _create_deal("Decision Queue Missing Docs Co")
        self._seed_missing_docs(deal_id)

        resp = client.get(f"/api/v1/deals/{deal_id}/decision-queue")
        body = resp.json()
        assert body["readiness"] == "Ready"
        assert any(i["source_tab"] == "documents" for i in body["items"])
        assert all(not i["blocking"] for i in body["items"] if i["source_tab"] == "documents")

    def test_resolved_inquiry_is_excluded_even_if_blocking(self):
        deal_id = _create_deal("Decision Queue Resolved Inquiry Co")
        created = client.post(
            f"/api/v1/deals/{deal_id}/inquiries",
            json={"request": "X", "due_date": "2026-03-01", "blocking": True},
        ).json()
        client.patch(f"/api/v1/deals/{deal_id}/inquiries/{created['id']}", json={"status": "Resolved"})

        resp = client.get(f"/api/v1/deals/{deal_id}/decision-queue")
        body = resp.json()
        assert body["items"] == []
        assert body["readiness"] == "Ready"

    def test_get_404_for_unknown_deal(self):
        resp = client.get("/api/v1/deals/no-such-deal/decision-queue")
        assert resp.status_code == 404
