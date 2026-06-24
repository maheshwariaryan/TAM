"""
Full HTTP flow tests for the Financial Statements API.

Tests the end-to-end path:
  POST /deals → upload sample_gl.csv → /process (ingestion) → /process (financial_builder)
  → poll status → assert GET /financials/* responses

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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _create_deal(name: str = "Financials Test Co") -> str:
    resp = client.post("/api/v1/deals", json={
        "company_name": name,
        "deal_name": f"{name} — FB Test",
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


def _poll_stage(deal_id: str, stage: str, timeout: int = 60) -> dict:
    for _ in range(timeout * 2):  # poll every 0.5 s
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
    Create one deal, upload GL, run ingestion + financial_builder.
    Scoped to module so all test classes reuse the same processed deal.
    """
    deal_id = _create_deal("Shared Financials Fixture Co")
    _upload_gl(deal_id)

    _run_stage(deal_id, "ingestion")
    _poll_stage(deal_id, "ingestion")

    _run_stage(deal_id, "financial_builder")
    _poll_stage(deal_id, "financial_builder")

    return {"deal_id": deal_id}


# ── P&L endpoint tests ─────────────────────────────────────────────────────────

class TestPnLEndpoint:
    def test_pnl_200(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        resp = client.get(f"/api/v1/deals/{deal_id}/financials/pnl")
        assert resp.status_code == 200

    def test_pnl_36_periods(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        pnl = client.get(f"/api/v1/deals/{deal_id}/financials/pnl").json()
        assert len(pnl["periods"]) == 36

    def test_pnl_revenue_positive_all_periods(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        pnl = client.get(f"/api/v1/deals/{deal_id}/financials/pnl").json()
        for pk, rev in pnl["revenue"].items():
            assert Decimal(rev) > 0, f"Revenue non-positive in {pk}"

    def test_pnl_gross_profit_reasonable(self, processed_deal):
        """Spot-check January 2022 gross profit > 0 (company is not operating at loss)."""
        deal_id = processed_deal["deal_id"]
        pnl = client.get(f"/api/v1/deals/{deal_id}/financials/pnl").json()
        gp = Decimal(pnl["gross_profit"]["2022-01"])
        assert gp > 0, "Gross profit should be positive for January 2022"

    def test_pnl_period_filter_by_year(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        pnl = client.get(
            f"/api/v1/deals/{deal_id}/financials/pnl", params={"period": "2023"}
        ).json()
        assert len(pnl["periods"]) == 12
        for p in pnl["periods"]:
            assert p.startswith("2023"), f"Period {p} not in 2023"

    def test_pnl_period_filter_single_month(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        pnl = client.get(
            f"/api/v1/deals/{deal_id}/financials/pnl", params={"period": "2023-06"}
        ).json()
        assert len(pnl["periods"]) == 1
        assert pnl["periods"][0] == "2023-06-01"

    def test_pnl_annual_rollup_3_years(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        pnl = client.get(
            f"/api/v1/deals/{deal_id}/financials/pnl", params={"period": "annual"}
        ).json()
        assert len(pnl["periods"]) == 3, f"Expected 3 annual periods, got {len(pnl['periods'])}"
        years = {p[:4] for p in pnl["periods"]}
        assert years == {"2022", "2023", "2024"}

    def test_pnl_annual_revenue_is_12x_monthly(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        # Fetch all months (summary dicts contain all 36 periods)
        monthly = client.get(f"/api/v1/deals/{deal_id}/financials/pnl").json()
        annual = client.get(
            f"/api/v1/deals/{deal_id}/financials/pnl", params={"period": "annual"}
        ).json()

        # Only sum 2022 months from the monthly revenue dict
        monthly_2022_sum = sum(
            Decimal(v) for k, v in monthly["revenue"].items() if k.startswith("2022")
        )
        annual_2022_rev = Decimal(annual["revenue"]["2022"])
        # Allow small rounding differences (Decimal arithmetic is exact here so should be 0)
        assert abs(monthly_2022_sum - annual_2022_rev) < Decimal("1.00"), (
            f"Annual 2022 revenue {annual_2022_rev} doesn't match "
            f"sum of monthly 2022 values {monthly_2022_sum}"
        )


# ── Balance Sheet endpoint tests ───────────────────────────────────────────────

class TestBalanceSheetEndpoint:
    def test_bs_200(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        resp = client.get(f"/api/v1/deals/{deal_id}/financials/balance-sheet")
        assert resp.status_code == 200

    def test_bs_36_periods(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        bs = client.get(f"/api/v1/deals/{deal_id}/financials/balance-sheet").json()
        assert len(bs["periods"]) == 36

    def test_bs_balanced_all_periods(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        bs = client.get(f"/api/v1/deals/{deal_id}/financials/balance-sheet").json()
        for pk, balanced in bs["is_balanced"].items():
            assert balanced, f"Balance sheet does not balance in period {pk}"

    def test_bs_total_assets_positive(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        bs = client.get(f"/api/v1/deals/{deal_id}/financials/balance-sheet").json()
        for pk, assets in bs["total_assets"].items():
            assert Decimal(assets) > 0, f"Total assets non-positive in {pk}"

    def test_bs_assets_eq_liab_plus_equity(self, processed_deal):
        """Verify the JSON numbers match the accounting identity (belt-and-suspenders)."""
        deal_id = processed_deal["deal_id"]
        bs = client.get(f"/api/v1/deals/{deal_id}/financials/balance-sheet").json()
        tolerance = Decimal("0.10")
        for pk in bs["total_assets"]:
            assets = Decimal(bs["total_assets"][pk])
            liab = Decimal(bs["total_liabilities"][pk])
            equity = Decimal(bs["total_equity"][pk])
            diff = abs(assets - (liab + equity))
            assert diff <= tolerance, f"A = L + E gap ${diff:.2f} in {pk}"


# ── Cash Flow endpoint tests ───────────────────────────────────────────────────

class TestCashFlowEndpoint:
    def test_cf_200(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        resp = client.get(f"/api/v1/deals/{deal_id}/financials/cash-flow")
        assert resp.status_code == 200

    def test_cf_36_periods(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        cf = client.get(f"/api/v1/deals/{deal_id}/financials/cash-flow").json()
        assert len(cf["periods"]) == 36

    def test_cf_operating_keys_present(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        cf = client.get(f"/api/v1/deals/{deal_id}/financials/cash-flow").json()
        assert "operating_cash_flow" in cf
        assert len(cf["operating_cash_flow"]) == 36

    def test_cf_rows_valid_sections(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        cf = client.get(f"/api/v1/deals/{deal_id}/financials/cash-flow").json()
        valid = {"Operating", "Investing", "Financing"}
        for row in cf["rows"]:
            assert row["section"] in valid, f"Invalid section: {row['section']}"


# ── Summary endpoint tests ─────────────────────────────────────────────────────

class TestSummaryEndpoint:
    def test_summary_200(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        resp = client.get(f"/api/v1/deals/{deal_id}/financials/summary")
        assert resp.status_code == 200

    def test_summary_has_required_keys(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        summary = client.get(f"/api/v1/deals/{deal_id}/financials/summary").json()
        assert "revenue" in summary
        assert "ebitda" in summary
        assert "ebitda_margin_pct" in summary
        assert "gross_margin_pct" in summary

    def test_summary_36_periods(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        summary = client.get(f"/api/v1/deals/{deal_id}/financials/summary").json()
        assert len(summary["periods"]) == 36

    def test_summary_ebitda_margin_reasonable(self, processed_deal):
        deal_id = processed_deal["deal_id"]
        summary = client.get(f"/api/v1/deals/{deal_id}/financials/summary").json()
        for pk, margin in summary["ebitda_margin_pct"].items():
            assert -50 <= margin <= 50, f"EBITDA margin {margin:.1f}% out of range in {pk}"


# ── 404 before processing ──────────────────────────────────────────────────────

class TestFinancialsNotReady:
    def test_pnl_404_before_processing(self):
        deal_id = _create_deal("Unprocessed Co")
        _upload_gl(deal_id)
        resp = client.get(f"/api/v1/deals/{deal_id}/financials/pnl")
        assert resp.status_code == 404

    def test_bs_404_before_processing(self):
        deal_id = _create_deal("Unprocessed BS Co")
        _upload_gl(deal_id)
        resp = client.get(f"/api/v1/deals/{deal_id}/financials/balance-sheet")
        assert resp.status_code == 404
