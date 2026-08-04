"""
Deal-scoped settings API tests: GET default/round-trip, PATCH partial update.
IDOR coverage lives in test_authorization.py (GET in the shared sweep,
PATCH in TestDealScopedMutatingEndpointsBlockNonOwner).
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
from tests.auth_helpers import authenticate as _authenticate  # noqa: E402

_authenticate(client)


def _create_deal(name: str) -> str:
    resp = client.post(
        "/api/v1/deals",
        json={"company_name": name, "deal_name": f"{name} — Settings Test", "currency": "USD"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["deal_id"]


class TestSettingsEndpoint:
    def test_get_returns_today_defaults_when_none_configured(self):
        deal_id = _create_deal("Settings Default Co")
        resp = client.get(f"/api/v1/deals/{deal_id}/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["materiality_threshold"] == 75_000.0
        assert body["tie_out_tolerance_pct"] == 0.50
        assert body["cash_conversion_medium_pct"] == 60.0
        assert body["cash_conversion_high_pct"] == 30.0
        assert body["cash_conversion_critical_pct"] == 0.0

    def test_patch_partial_update_merges_onto_current(self):
        deal_id = _create_deal("Settings Partial Co")
        resp = client.patch(
            f"/api/v1/deals/{deal_id}/settings", json={"materiality_threshold": 100_000}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["materiality_threshold"] == 100_000
        # Untouched fields keep their defaults
        assert body["tie_out_tolerance_pct"] == 0.50

        get_resp = client.get(f"/api/v1/deals/{deal_id}/settings")
        assert get_resp.json()["materiality_threshold"] == 100_000

    def test_patch_then_patch_again_merges_not_replaces(self):
        deal_id = _create_deal("Settings Merge Co")
        client.patch(f"/api/v1/deals/{deal_id}/settings", json={"tie_out_tolerance_pct": 1.0})
        second = client.patch(
            f"/api/v1/deals/{deal_id}/settings", json={"materiality_threshold": 50_000}
        )
        assert second.status_code == 200
        body = second.json()
        assert body["materiality_threshold"] == 50_000
        assert body["tie_out_tolerance_pct"] == 1.0  # from the first PATCH, not reset

    def test_patch_rejects_invalid_band_ordering(self):
        deal_id = _create_deal("Settings Invalid Bands Co")
        resp = client.patch(
            f"/api/v1/deals/{deal_id}/settings",
            json={"cash_conversion_high_pct": 90.0},  # > default medium (60) -> invalid ordering
        )
        assert resp.status_code == 422

    def test_get_404_for_unknown_deal(self):
        resp = client.get("/api/v1/deals/no-such-deal/settings")
        assert resp.status_code == 404
