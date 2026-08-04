"""
IDOR regression test — the actual concern that prompted this whole security
pass ("altering the URL, one user should not be able to access another
user's work").

User A creates a deal. User B (a separate signed-up account) must be denied
on every deal-scoped endpoint for that deal_id — 404 (never 200, and never
403, since require_deal_owner deliberately returns 404 for both "doesn't
exist" and "not yours" to avoid confirming a deal_id is valid to a caller who
doesn't own it). An unauthenticated caller must get 401 before even reaching
that check.
"""

from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import authenticate

# (method, path template) for every deal-scoped endpoint. GET-only where the
# request has no side effects on the shared deal; a handful of POSTs are
# covered separately below since they need bodies/files.
_DEAL_SCOPED_GET_ENDPOINTS = [
    "/api/v1/deals/{deal_id}",
    "/api/v1/deals/{deal_id}/status",
    "/api/v1/deals/{deal_id}/documents",
    "/api/v1/deals/{deal_id}/gl/lines",
    "/api/v1/deals/{deal_id}/gl/validation",
    "/api/v1/deals/{deal_id}/gl/periods",
    "/api/v1/deals/{deal_id}/financials/pnl",
    "/api/v1/deals/{deal_id}/financials/balance-sheet",
    "/api/v1/deals/{deal_id}/financials/cash-flow",
    "/api/v1/deals/{deal_id}/financials/summary",
    "/api/v1/deals/{deal_id}/qoe",
    "/api/v1/deals/{deal_id}/redflags",
    "/api/v1/deals/{deal_id}/redflags/summary",
    "/api/v1/deals/{deal_id}/nwc",
    "/api/v1/deals/{deal_id}/commercial",
    "/api/v1/deals/{deal_id}/net-debt",
    "/api/v1/deals/{deal_id}/dcf",
    "/api/v1/deals/{deal_id}/contracts",
    "/api/v1/deals/{deal_id}/narrative",
    "/api/v1/deals/{deal_id}/tie-outs",
    "/api/v1/deals/{deal_id}/notes",
    "/api/v1/deals/{deal_id}/settings",
    "/api/v1/deals/{deal_id}/inquiries",
    "/api/v1/deals/{deal_id}/decision-queue",
]


def _create_deal(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/deals",
        json={"company_name": "Victim Co", "deal_name": "IDOR Test Deal", "currency": "USD"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["deal_id"]


class TestDealScopedGetEndpointsBlockNonOwner:
    def test_every_get_endpoint_returns_404_for_non_owner(self):
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)

        attacker_client = TestClient(app)
        authenticate(attacker_client)

        for path_template in _DEAL_SCOPED_GET_ENDPOINTS:
            path = path_template.format(deal_id=deal_id)
            resp = attacker_client.get(path)
            assert resp.status_code == 404, (
                f"{path} leaked to a non-owner: got {resp.status_code}, expected 404"
            )

    def test_every_get_endpoint_returns_401_when_unauthenticated(self):
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)

        anon_client = TestClient(app)  # no signup/login at all

        for path_template in _DEAL_SCOPED_GET_ENDPOINTS:
            path = path_template.format(deal_id=deal_id)
            resp = anon_client.get(path)
            assert resp.status_code == 401, (
                f"{path} allowed an unauthenticated caller: got {resp.status_code}, expected 401"
            )

    def test_owner_gets_a_non_404_response(self):
        """Sanity check that require_deal_owner isn't blocking everyone — the
        owner should get past the ownership check (200, or a legitimate
        404/other status from downstream 'no data yet' logic, but reached via
        their own deal, not blocked at the auth layer)."""
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)

        resp = owner_client.get(f"/api/v1/deals/{deal_id}")
        assert resp.status_code == 200
        assert resp.json()["deal_id"] == deal_id


class TestDealListingScopedToOwner:
    def test_list_deals_excludes_other_users_deals(self):
        user_a = TestClient(app)
        authenticate(user_a)
        deal_a = _create_deal(user_a)

        user_b = TestClient(app)
        authenticate(user_b)
        deal_b = _create_deal(user_b)

        resp_a = user_a.get("/api/v1/deals")
        assert resp_a.status_code == 200
        ids_a = {d["deal_id"] for d in resp_a.json()}
        assert deal_a in ids_a
        assert deal_b not in ids_a

        resp_b = user_b.get("/api/v1/deals")
        ids_b = {d["deal_id"] for d in resp_b.json()}
        assert deal_b in ids_b
        assert deal_a not in ids_b

    def test_list_deals_requires_auth(self):
        anon_client = TestClient(app)
        resp = anon_client.get("/api/v1/deals")
        assert resp.status_code == 401


class TestDealScopedMutatingEndpointsBlockNonOwner:
    def test_upload_blocked_for_non_owner(self):
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)

        attacker_client = TestClient(app)
        authenticate(attacker_client)

        resp = attacker_client.post(
            f"/api/v1/deals/{deal_id}/upload",
            files=[("files", ("evil.csv", b"account_code,amount\n1,2\n", "text/csv"))],
        )
        assert resp.status_code == 404

    def test_process_blocked_for_non_owner(self):
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)

        attacker_client = TestClient(app)
        authenticate(attacker_client)

        resp = attacker_client.post(
            f"/api/v1/deals/{deal_id}/process", json={"stages": ["ingestion"]}
        )
        assert resp.status_code == 404

    def test_contracts_analyze_blocked_for_non_owner(self):
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)

        attacker_client = TestClient(app)
        authenticate(attacker_client)

        resp = attacker_client.post(f"/api/v1/deals/{deal_id}/contracts/analyze")
        assert resp.status_code == 404

    def test_narrative_generate_blocked_for_non_owner(self):
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)

        attacker_client = TestClient(app)
        authenticate(attacker_client)

        resp = attacker_client.post(f"/api/v1/deals/{deal_id}/narrative/generate")
        assert resp.status_code == 404

    def test_databook_export_blocked_for_non_owner(self):
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)

        attacker_client = TestClient(app)
        authenticate(attacker_client)

        resp = attacker_client.post(f"/api/v1/deals/{deal_id}/databook/export")
        assert resp.status_code == 404

    def test_notes_save_blocked_for_non_owner(self):
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)

        attacker_client = TestClient(app)
        authenticate(attacker_client)

        resp = attacker_client.put(
            f"/api/v1/deals/{deal_id}/notes", json={"notes": "attacker note", "report_draft": []}
        )
        assert resp.status_code == 404

    def test_settings_patch_blocked_for_non_owner(self):
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)

        attacker_client = TestClient(app)
        authenticate(attacker_client)

        resp = attacker_client.patch(
            f"/api/v1/deals/{deal_id}/settings", json={"materiality_threshold": 1}
        )
        assert resp.status_code == 404

    def test_inquiry_create_blocked_for_non_owner(self):
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)

        attacker_client = TestClient(app)
        authenticate(attacker_client)

        resp = attacker_client.post(
            f"/api/v1/deals/{deal_id}/inquiries",
            json={"request": "attacker inquiry", "due_date": "2026-03-01"},
        )
        assert resp.status_code == 404

    def test_inquiry_patch_and_delete_blocked_for_non_owner(self):
        owner_client = TestClient(app)
        authenticate(owner_client)
        deal_id = _create_deal(owner_client)
        created = owner_client.post(
            f"/api/v1/deals/{deal_id}/inquiries",
            json={"request": "owner inquiry", "due_date": "2026-03-01"},
        ).json()

        attacker_client = TestClient(app)
        authenticate(attacker_client)

        patch_resp = attacker_client.patch(
            f"/api/v1/deals/{deal_id}/inquiries/{created['id']}", json={"status": "Resolved"}
        )
        assert patch_resp.status_code == 404

        delete_resp = attacker_client.delete(f"/api/v1/deals/{deal_id}/inquiries/{created['id']}")
        assert delete_resp.status_code == 404
