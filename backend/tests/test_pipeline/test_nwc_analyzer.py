"""
Step 6 tests — NWC Analyzer + Commercial Health.

All run with USE_MOCK_LLM=true (no API cost).
Key assertions:
  - NWC data points reconcile to the balance sheet (Current Assets - Current Liabilities,
    restricted to NWC_COMPONENTS categories)
  - Peg math: ltm_average / median_trailing_12 always present; exactly one recommended
  - Missing AR/AP aging degrades status to "partial" without raising
  - No balance sheet degrades status to "skipped"
  - NWC volatility and revenue seasonality red-flag rules fire on synthetic data
    and stay silent on the well-behaved fixture
  - Full HTTP flow: /process → GET /nwc and /commercial return real numbers
"""

import asyncio
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.coa_mapper import CoAMapperAgent
from app.main import app
from app.pipeline.financial_builder import balance_sheet as bs_builder
from app.pipeline.financial_builder.orchestrator import _apply_classifications
from app.pipeline.ingestion.loader import infer_column_map, load_file
from app.pipeline.ingestion.normalizer import normalise
from app.pipeline.nwc_analyzer import orchestrator as nwc_orch
from app.pipeline.redflag_detector import rules as rf_rules
from app.schemas.aging import AgingReport, AgingSummary
from app.schemas.financials import PnLStatement
from app.schemas.nwc import NWCReport

FIXTURES = Path(__file__).parent.parent / "fixtures"
FIXTURE_GL = FIXTURES / "sample_gl.csv"
DEAL_ID = "test-step6-001"

client = TestClient(app)
from tests.auth_helpers import authenticate as _authenticate  # noqa: E402

_authenticate(client)


def _build_mapped_bs_pnl():
    df = load_file(FIXTURE_GL)
    col_map = infer_column_map(df)
    raw = normalise(df, col_map, "sample_gl.csv", DEAL_ID)
    unique_pairs = list({(gl.account_code, gl.account_description) for gl in raw})
    agent = CoAMapperAgent()
    cls_map = asyncio.run(agent.map_accounts(unique_pairs))
    mapped = _apply_classifications(raw, cls_map)

    from app.pipeline.financial_builder import pnl as pnl_builder
    pnl = pnl_builder.build(mapped)
    bs = bs_builder.build(mapped)
    return mapped, pnl, bs


def _make_aging(deal_id: str, doc_type: str, period: date, total: Decimal) -> AgingReport:
    return AgingReport(
        deal_id=deal_id,
        document_type=doc_type,
        summaries=[
            AgingSummary(
                deal_id=deal_id,
                document_type=doc_type,
                period=period,
                bucket_0_30=total * Decimal("0.6"),
                bucket_31_60=total * Decimal("0.2"),
                bucket_61_90=total * Decimal("0.1"),
                bucket_90_plus=total * Decimal("0.1"),
                total=total,
                source_file=f"{doc_type}.csv",
                source_row=1,
            )
        ],
    )


class TestNWCDataPoints:
    @classmethod
    def setup_class(cls):
        cls.mapped, cls.pnl, cls.bs = _build_mapped_bs_pnl()

    def test_36_data_points(self):
        points = nwc_orch._build_data_points(self.bs, self.pnl)
        assert len(points) == 36

    def test_nwc_equals_current_assets_minus_current_liabilities(self):
        points = nwc_orch._build_data_points(self.bs, self.pnl)
        dp = points[-1]
        expected = (
            dp.accounts_receivable + dp.inventory + dp.prepaid_expenses + dp.other_current_assets
        ) - (
            dp.accounts_payable + dp.accrued_liabilities + dp.deferred_revenue
            + dp.current_debt + dp.other_current_liabilities
        )
        assert dp.net_working_capital == expected

    def test_nwc_as_pct_revenue_populated(self):
        points = nwc_orch._build_data_points(self.bs, self.pnl)
        assert all(dp.nwc_as_pct_revenue is not None for dp in points)


class TestNWCPegs:
    @classmethod
    def setup_class(cls):
        cls.mapped, cls.pnl, cls.bs = _build_mapped_bs_pnl()
        cls.points = nwc_orch._build_data_points(cls.bs, cls.pnl)
        cls.monthly_nwc = {dp.period.strftime("%Y-%m"): dp.net_working_capital for dp in cls.points}

    def test_at_least_two_pegs_computed(self):
        pegs = nwc_orch._compute_pegs(self.monthly_nwc)
        methods = {p.method for p in pegs}
        assert {"ltm_average", "median_trailing_12"}.issubset(methods)

    def test_exactly_one_recommended(self):
        pegs = nwc_orch._compute_pegs(self.monthly_nwc)
        recommended = [p for p in pegs if p.recommended]
        assert len(recommended) == 1

    def test_seasonal_adjusted_present_with_36_months(self):
        # 36 months >= 24-month threshold, so the seasonal candidate must be offered
        pegs = nwc_orch._compute_pegs(self.monthly_nwc)
        methods = {p.method for p in pegs}
        assert "seasonal_adjusted" in methods

    def test_ci_bounds_bracket_peg_amount(self):
        pegs = nwc_orch._compute_pegs(self.monthly_nwc)
        for peg in pegs:
            assert peg.confidence_interval_low <= peg.peg_amount <= peg.confidence_interval_high


class TestNWCReportDegradation:
    @classmethod
    def setup_class(cls):
        cls.mapped, cls.pnl, cls.bs = _build_mapped_bs_pnl()

    def test_skipped_without_balance_sheet(self):
        report = nwc_orch._build_nwc_report("deal-x", None, self.pnl, None, None)
        assert report.status == "skipped"
        assert report.data_points == []

    def test_partial_without_aging(self):
        report = nwc_orch._build_nwc_report(DEAL_ID, self.bs, self.pnl, None, None)
        assert report.status == "partial"
        assert report.has_ar_aging is False
        assert report.has_ap_aging is False
        assert len(report.data_points) == 36
        assert report.ratios is not None
        assert report.ratios.ar_over_60d_pct is None

    def test_complete_with_aging(self):
        last_period = sorted(self.bs.periods)[-1]
        ar = _make_aging(DEAL_ID, "ar_aging", last_period, Decimal("262000"))
        ap = _make_aging(DEAL_ID, "ap_aging", last_period, Decimal("143000"))
        report = nwc_orch._build_nwc_report(DEAL_ID, self.bs, self.pnl, ar, ap)
        assert report.status == "complete"
        assert report.ratios.ar_over_60d_pct == pytest.approx(20.0)
        assert report.ratios.ap_over_60d_pct == pytest.approx(20.0)

    def test_ratios_dso_dpo_dio_computed(self):
        report = nwc_orch._build_nwc_report(DEAL_ID, self.bs, self.pnl, None, None)
        r = report.ratios
        assert r.dso_days is not None and r.dso_days > 0
        assert r.dpo_days is not None and r.dpo_days > 0
        assert r.dio_days is not None and r.dio_days > 0
        assert r.cash_conversion_cycle_days == pytest.approx(r.dso_days + r.dio_days - r.dpo_days)


class TestCommercialHealthReport:
    @classmethod
    def setup_class(cls):
        cls.mapped, cls.pnl, cls.bs = _build_mapped_bs_pnl()

    def test_skipped_without_pnl(self):
        report = nwc_orch._build_commercial_report("deal-x", None)
        assert report.status == "skipped"

    def test_growth_and_margins_present(self):
        report = nwc_orch._build_commercial_report(DEAL_ID, self.pnl)
        assert report.status == "partial"
        assert len(report.revenue_growth_yoy_pct) >= 1
        assert len(report.gross_margin_trend_pct) == 36
        assert len(report.ebitda_margin_trend_pct) == 36

    def test_customer_metrics_marked_unavailable_not_faked(self):
        report = nwc_orch._build_commercial_report(DEAL_ID, self.pnl)
        assert any("customer" in m.lower() for m in report.unavailable_metrics)
        assert not hasattr(report, "customer_concentration_pct")


class TestNWCVolatilityRedFlag:
    def test_fires_above_threshold(self):
        report = NWCReport(
            deal_id=DEAL_ID,
            status="complete",
            message="x",
            data_points=[],
            nwc_volatility=0.45,
        )
        flags = rf_rules._rule_nwc_volatility(DEAL_ID, report)
        assert len(flags) == 1
        assert flags[0].severity == "Medium"
        assert flags[0].rule_id == "NWC_VOLATILITY"

    def test_silent_below_threshold(self):
        report = NWCReport(deal_id=DEAL_ID, status="complete", message="x", nwc_volatility=0.10)
        assert rf_rules._rule_nwc_volatility(DEAL_ID, report) == []

    def test_silent_when_volatility_none(self):
        report = NWCReport(deal_id=DEAL_ID, status="skipped", message="x", nwc_volatility=None)
        assert rf_rules._rule_nwc_volatility(DEAL_ID, report) == []


class TestRevenueSeasonalityRedFlag:
    def test_silent_on_flat_fixture(self):
        _, pnl, _ = _build_mapped_bs_pnl()
        # The Acme fixture has no planted seasonality — rule should stay quiet
        assert rf_rules._rule_revenue_seasonality(DEAL_ID, pnl) == []

    def test_fires_on_synthetic_q4_concentration(self):
        periods = [date(2023, m, 1) for m in range(1, 13)]
        revenue = {p.strftime("%Y-%m"): Decimal("100000") for p in periods}
        for p in periods:
            if p.month in (10, 11, 12):
                revenue[p.strftime("%Y-%m")] = Decimal("400000")
        pnl = PnLStatement(
            deal_id=DEAL_ID,
            periods=periods,
            rows=[],
            revenue=revenue,
            gross_profit=revenue,
            ebitda=revenue,
            ebit=revenue,
            net_income=revenue,
            gross_margin={k: 1.0 for k in revenue},
            ebitda_margin={k: 1.0 for k in revenue},
        )
        flags = rf_rules._rule_revenue_seasonality(DEAL_ID, pnl)
        assert len(flags) == 1
        assert flags[0].severity == "Informational"
        assert flags[0].rule_id == "REVENUE_SEASONALITY"


# ─── Full HTTP flow ───────────────────────────────────────────────────────────

def _create_deal(name: str) -> str:
    resp = client.post("/api/v1/deals", json={
        "company_name": name, "deal_name": f"{name} — Step 6 Test", "currency": "USD",
    })
    assert resp.status_code == 201
    return resp.json()["deal_id"]


def _upload(deal_id: str, filenames: list[str]) -> None:
    files = [("files", (fn, open(FIXTURES / fn, "rb"), "text/csv")) for fn in filenames]
    resp = client.post(f"/api/v1/deals/{deal_id}/upload", files=files)
    assert resp.status_code == 200


def _run_stages(deal_id: str, stages: list[str]) -> None:
    resp = client.post(f"/api/v1/deals/{deal_id}/process", json={"stages": stages})
    assert resp.status_code == 200
    for _ in range(120):
        status = client.get(f"/api/v1/deals/{deal_id}/status").json()
        if all(status["stages"].get(s) == "complete" for s in stages):
            return
        if any(status["stages"].get(s) == "failed" for s in stages):
            pytest.fail(f"Pipeline failed: {status.get('error')}")
        time.sleep(0.5)
    pytest.fail("Pipeline timed out")


class TestNWCApiEndpoint:
    def test_nwc_and_commercial_endpoints_return_real_data(self):
        deal_id = _create_deal("NWC API Test Co")
        _upload(deal_id, ["sample_gl.csv", "sample_ar_aging.csv", "sample_ap_aging.csv"])
        _run_stages(deal_id, ["ingestion", "coa_mapping", "financial_builder", "nwc_analyzer"])

        nwc_resp = client.get(f"/api/v1/deals/{deal_id}/nwc")
        assert nwc_resp.status_code == 200
        nwc = nwc_resp.json()
        assert nwc["status"] == "complete"
        assert len(nwc["data_points"]) == 36
        assert len(nwc["pegs"]) >= 2
        assert nwc["ratios"]["dso_days"] is not None

        commercial_resp = client.get(f"/api/v1/deals/{deal_id}/commercial")
        assert commercial_resp.status_code == 200
        commercial = commercial_resp.json()
        assert commercial["status"] == "partial"
        assert len(commercial["unavailable_metrics"]) > 0

    def test_nwc_404_before_processing(self):
        deal_id = _create_deal("NWC 404 Test Co")
        resp = client.get(f"/api/v1/deals/{deal_id}/nwc")
        assert resp.status_code == 404
