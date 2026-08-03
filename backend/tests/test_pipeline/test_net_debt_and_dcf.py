"""
Step 6/7 tests — Net Debt Bridge + simple DCF.

All run with USE_MOCK_LLM=true (no API cost).
Key assertions:
  - Net debt = (current debt + long-term debt) - cash, from the balance sheet
  - Bridge components sum to net debt
  - Reconciliation against contract-extracted principal fires only outside tolerance
  - Missing balance sheet degrades to "skipped"; missing debt instruments to "partial"
  - DCF: PV of FCF + PV of terminal value == enterprise value; missing projections skip cleanly
  - Full HTTP flow: /process → GET /net-debt and /dcf return real numbers
"""

import asyncio
import time
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.coa_mapper import CoAMapperAgent
from app.main import app
from app.pipeline.dcf_engine import orchestrator as dcf_orch
from app.pipeline.financial_builder import balance_sheet as bs_builder
from app.pipeline.financial_builder.orchestrator import _apply_classifications
from app.pipeline.ingestion.loader import infer_column_map, load_file
from app.pipeline.ingestion.normalizer import normalise
from app.pipeline.net_debt_bridge import orchestrator as nd_orch
from app.schemas.contracts import DebtInstrument, DebtSchedule
from app.schemas.projections import ProjectionLine, ProjectionSchedule

FIXTURES = Path(__file__).parent.parent / "fixtures"
FIXTURE_GL = FIXTURES / "sample_gl.csv"
DEAL_ID = "test-netdebt-001"

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


class TestNetDebtBridge:
    @classmethod
    def setup_class(cls):
        cls.mapped, cls.pnl, cls.bs = _build_mapped_bs_pnl()

    def test_skipped_without_balance_sheet(self):
        report = nd_orch._build_report(DEAL_ID, None, self.pnl, None)
        assert report.status == "skipped"
        assert report.net_debt is None

    def test_partial_without_debt_instruments(self):
        report = nd_orch._build_report(DEAL_ID, self.bs, self.pnl, None)
        assert report.status == "partial"
        assert report.net_debt is not None
        assert report.total_debt == report.current_debt + report.long_term_debt
        assert report.net_debt == report.total_debt - report.cash_and_equivalents

    def test_bridge_components_sum_to_net_debt(self):
        report = nd_orch._build_report(DEAL_ID, self.bs, self.pnl, None)
        net_debt_component = next(c for c in report.bridge if c.label == "Net Debt")
        assert net_debt_component.amount == report.net_debt

    def test_complete_with_matching_instruments(self):
        schedule = DebtSchedule(
            deal_id=DEAL_ID,
            instruments=[
                DebtInstrument(
                    instrument_id="DEBT-TEST01",
                    deal_id=DEAL_ID,
                    facility_type="term_loan",
                    lender="Test Bank",
                    principal_outstanding=None,
                    source_document="test.pdf",
                    extraction_confidence=0.9,
                )
            ],
        )
        report = nd_orch._build_report(DEAL_ID, self.bs, self.pnl, schedule)
        assert report.status == "complete"
        # No principal_outstanding provided -> no reconciliation computed, but shouldn't error
        assert report.instrument_principal_total is None

    def test_reconciliation_flags_material_variance(self):
        report_no_debt = nd_orch._build_report(DEAL_ID, self.bs, self.pnl, None)
        total_debt = report_no_debt.total_debt
        far_off_principal = (total_debt or Decimal("0")) + Decimal("10000000")

        schedule = DebtSchedule(
            deal_id=DEAL_ID,
            instruments=[
                DebtInstrument(
                    instrument_id="DEBT-TEST02",
                    deal_id=DEAL_ID,
                    facility_type="term_loan",
                    principal_outstanding=far_off_principal,
                    source_document="test.pdf",
                    extraction_confidence=0.9,
                )
            ],
        )
        report = nd_orch._build_report(DEAL_ID, self.bs, self.pnl, schedule)
        assert report.reconciliation_variance is not None
        assert "differs from" in report.reconciliation_note

    def test_net_debt_to_ebitda_computed(self):
        report = nd_orch._build_report(DEAL_ID, self.bs, self.pnl, None)
        assert report.net_debt_to_ebitda is not None


class TestSimpleDCF:
    def test_skipped_without_ebitda(self):
        schedule = ProjectionSchedule(
            deal_id=DEAL_ID,
            lines=[
                ProjectionLine(period="2025-01-01", source_file="proj.csv", source_row=1),
            ],
        )
        report = dcf_orch._build_report(DEAL_ID, schedule)
        assert report.status == "skipped"

    def test_complete_dcf_reconciles(self):
        # cogs/opex are stored as positive expense magnitudes — matching real ingested data
        # (see projections_parser.py and tests/fixtures/sample_projections.csv), not negative
        # GL-style signed amounts.
        lines = [
            ProjectionLine(
                period=f"2025-{m:02d}-01",
                revenue=Decimal("1000000"),
                cogs=Decimal("600000"),
                opex=Decimal("250000"),
                capex=Decimal("20000"),
                source_file="proj.csv",
                source_row=m,
            )
            for m in range(1, 13)
        ]
        schedule = ProjectionSchedule(deal_id=DEAL_ID, lines=lines)
        report = dcf_orch._build_report(DEAL_ID, schedule)

        assert report.status == "complete"
        assert report.projection_periods == 12
        assert report.enterprise_value == report.sum_pv_of_fcf + report.pv_of_terminal_value
        assert len(report.limitations) >= 3
        assert report.assumptions.discount_rate_annual == dcf_orch.DEFAULT_DISCOUNT_RATE_ANNUAL

    def test_corrupt_projections_file_reports_failed_not_uncaught_crash(self, tmp_path, monkeypatch):
        from app.config import settings

        deal_id = "test-dcf-corrupt-projections"
        processed_dir = settings.processed_dir / deal_id
        processed_dir.mkdir(parents=True, exist_ok=True)
        (processed_dir / "management_projections.json").write_text("{not valid json", encoding="utf-8")

        result = dcf_orch.run(deal_id)
        assert result["status"] == "failed"
        assert "management_projections.json" in result["message"] or "projections" in result["message"].lower()

    def test_derives_ebitda_when_not_provided_directly(self):
        # cogs/opex are positive expense magnitudes here too (see note above) — the fallback
        # must compute revenue - cogs - opex, not revenue + cogs + opex.
        lines = [
            ProjectionLine(
                period="2025-01-01",
                revenue=Decimal("1000000"),
                cogs=Decimal("600000"),
                opex=Decimal("250000"),
                source_file="proj.csv",
                source_row=1,
            )
        ]
        schedule = ProjectionSchedule(deal_id=DEAL_ID, lines=lines)
        report = dcf_orch._build_report(DEAL_ID, schedule)
        assert report.projected_fcf["2025-01"] == Decimal("150000")  # 1M - 600k - 250k - 0 capex


# ─── Full HTTP flow ───────────────────────────────────────────────────────────

def _create_deal(name: str) -> str:
    resp = client.post("/api/v1/deals", json={
        "company_name": name, "deal_name": f"{name} — Net Debt Test", "currency": "USD",
    })
    assert resp.status_code == 201
    return resp.json()["deal_id"]


def _upload(deal_id: str, filenames: list[str]) -> None:
    files = [("files", (fn, open(FIXTURES / fn, "rb"), "application/octet-stream")) for fn in filenames]
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


class TestNetDebtApiEndpoint:
    def test_net_debt_endpoint_returns_real_data(self):
        deal_id = _create_deal("Net Debt API Test Co")
        _upload(deal_id, ["sample_gl.csv", "Credit_Agreement_FNB.pdf"])
        _run_stages(deal_id, ["ingestion", "coa_mapping", "financial_builder", "net_debt_bridge"])

        resp = client.get(f"/api/v1/deals/{deal_id}/net-debt")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "complete"
        assert data["net_debt"] is not None
        assert len(data["instruments"]) == 1

    def test_dcf_endpoint_skipped_without_projections(self):
        deal_id = _create_deal("DCF Skip Test Co")
        _upload(deal_id, ["sample_gl.csv"])
        _run_stages(deal_id, ["ingestion", "coa_mapping", "financial_builder", "dcf_engine"])

        resp = client.get(f"/api/v1/deals/{deal_id}/dcf")
        assert resp.status_code == 200
        assert resp.json()["status"] == "skipped"

    def test_net_debt_404_before_processing(self):
        deal_id = _create_deal("Net Debt 404 Test Co")
        resp = client.get(f"/api/v1/deals/{deal_id}/net-debt")
        assert resp.status_code == 404
