"""
Deal-scoped notes API tests: GET default/round-trip, PUT full-replace.
IDOR coverage lives in test_authorization.py (GET in the shared sweep,
PUT in TestDealScopedMutatingEndpointsBlockNonOwner).
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
from tests.auth_helpers import authenticate as _authenticate  # noqa: E402

_authenticate(client)


def _create_deal(name: str) -> str:
    resp = client.post(
        "/api/v1/deals",
        json={"company_name": name, "deal_name": f"{name} — Notes Test", "currency": "USD"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["deal_id"]


class TestNotesEndpoint:
    def test_get_returns_empty_defaults_when_none_saved(self):
        deal_id = _create_deal("Notes Default Co")
        resp = client.get(f"/api/v1/deals/{deal_id}/notes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["deal_id"] == deal_id
        assert body["notes"] == ""
        assert body["report_draft"] == []

    def test_put_then_get_round_trips(self):
        deal_id = _create_deal("Notes Round Trip Co")
        put_resp = client.put(
            f"/api/v1/deals/{deal_id}/notes",
            json={"notes": "management confirmed no related-party balances", "report_draft": ["snippet a"]},
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["notes"] == "management confirmed no related-party balances"

        get_resp = client.get(f"/api/v1/deals/{deal_id}/notes")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["notes"] == "management confirmed no related-party balances"
        assert body["report_draft"] == ["snippet a"]

    def test_put_is_a_full_replace(self):
        deal_id = _create_deal("Notes Replace Co")
        client.put(f"/api/v1/deals/{deal_id}/notes", json={"notes": "first", "report_draft": ["a", "b"]})
        second = client.put(f"/api/v1/deals/{deal_id}/notes", json={"notes": "second", "report_draft": ["c"]})
        assert second.status_code == 200

        get_resp = client.get(f"/api/v1/deals/{deal_id}/notes")
        body = get_resp.json()
        assert body["notes"] == "second"
        assert body["report_draft"] == ["c"]

    def test_get_404_for_unknown_deal(self):
        resp = client.get("/api/v1/deals/no-such-deal/notes")
        assert resp.status_code == 404
