"""
Tests for the Group A/B/C schedule-file ingestion fix — the pipeline used to classify
balance_sheet_monthly.csv, debt_schedule.csv, payroll_headcount.csv, etc. as UNCLASSIFIED
and skip them entirely. This covers:
  - Content-based classification (must survive an arbitrary filename rename)
  - The wide/period-row schedule parsers
  - The debt_schedule.csv -> DebtInstrument parser
  - The Group C raw-table parser
  - cross_document_validator.reconcile_schedules (Pass/Fail tie-out behaviour)
  - Full ingestion + financial_builder end-to-end, and a contracts/analyze re-run
"""

import shutil
import time
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pipeline.ingestion import document_registry as registry
from app.pipeline.ingestion import orchestrator as ing_orch
from app.pipeline.ingestion.cross_document_validator import reconcile_schedules
from app.pipeline.ingestion.debt_schedule_parser import parse_debt_schedule_bytes
from app.pipeline.ingestion.loader import load_bytes
from app.pipeline.ingestion.schedule_parser import (
    parse_period_row_schedule_bytes,
    parse_wide_schedule_bytes,
)
from app.pipeline.ingestion.supporting_schedule_parser import parse_supporting_schedule_bytes
from app.schemas.documents import DocumentType
from app.schemas.financials import PnLStatement
from app.storage import file_store
from tests.auth_helpers import authenticate as _authenticate

FIXTURES = Path(__file__).parent.parent / "fixtures"

client = TestClient(app)
_authenticate(client)


def _classify(filename: str, content_filename: str | None = None):
    """Classify fixture bytes as if uploaded under `filename` (default: its own name)."""
    content_filename = content_filename or filename
    raw = (FIXTURES / filename).read_bytes()
    df = load_bytes(raw, content_filename)
    by_name, name_conf, _ = registry.classify_by_filename(content_filename)
    by_cols, col_conf = registry._sniff_columns(df, content_filename)
    sched = registry._sniff_schedule_content(df, content_filename)
    candidates = [(by_cols, col_conf)] + ([sched] if sched else [])
    best_type, best_conf = max(candidates, key=lambda c: c[1])
    if best_conf > name_conf:
        return best_type, best_conf
    return by_name, name_conf


class TestContentBasedClassification:
    @pytest.mark.parametrize(
        "filename,expected_type",
        [
            ("balance_sheet_monthly.csv", DocumentType.BALANCE_SHEET_SCHEDULE),
            ("income_statement_monthly.csv", DocumentType.INCOME_STATEMENT_SCHEDULE),
            ("cash_flow_statement.csv", DocumentType.CASH_FLOW_SCHEDULE),
            ("revenue_schedule.csv", DocumentType.REVENUE_SCHEDULE),
            ("cogs_schedule.csv", DocumentType.COGS_SCHEDULE),
            ("opex_schedule.csv", DocumentType.OPEX_SCHEDULE),
            ("debt_schedule.csv", DocumentType.DEBT_SCHEDULE),
            ("working_capital_schedule.csv", DocumentType.WORKING_CAPITAL_SCHEDULE),
            ("inventory_rollforward.csv", DocumentType.INVENTORY_ROLLFORWARD),
            ("lease_schedule.csv", DocumentType.LEASE_SCHEDULE),
            ("fixed_asset_register.csv", DocumentType.FIXED_ASSET_REGISTER),
            ("equity_rollforward_cap_table.csv", DocumentType.EQUITY_ROLLFORWARD),
            ("bank_statement_cashbook.csv", DocumentType.BANK_STATEMENT),
        ],
    )
    def test_real_fixture_classifies_correctly(self, filename, expected_type):
        doc_type, confidence = _classify(filename)
        assert doc_type == expected_type
        assert confidence >= 0.7

    def test_classification_survives_arbitrary_filename_rename(self, tmp_path):
        """Proves classification is content-based, not a re-hardcoded filename list."""
        renamed = tmp_path / "misc_export_final_v3.csv"
        shutil.copy(FIXTURES / "debt_schedule.csv", renamed)
        doc_type, confidence = _classify("debt_schedule.csv", content_filename=str(renamed))
        assert doc_type == DocumentType.DEBT_SCHEDULE
        assert confidence >= 0.9

    def test_gl_not_misclassified_as_account_level_schedule(self):
        """Regression test: a normal transaction-row GL also has account_code +
        account_description columns, which must not trigger the revenue/cogs/opex
        account-code-range signature (that requires genuine wide period-as-columns
        shape, which a GL file doesn't have)."""
        doc_type, _ = _classify("sample_gl.csv")
        assert doc_type == DocumentType.GENERAL_LEDGER

    def test_debt_agreement_filename_rule_is_pdf_only(self):
        """A CSV/XLSX named with 'debt' in it must not be shadowed into DEBT_AGREEMENT —
        only .pdf files get that treatment; debt_schedule.csv is structured data."""
        doc_type, _, _ = registry.classify_by_filename("debt_schedule.csv")
        assert doc_type != DocumentType.DEBT_AGREEMENT

    def test_unrecognizable_file_still_falls_back_to_unclassified(self):
        doc_type, _, detail = registry.classify_by_filename("totally_unknown_report.xyz")
        assert doc_type == DocumentType.UNCLASSIFIED
        assert detail is not None


class TestWideScheduleParser:
    def test_parses_balance_sheet_labels_and_periods(self):
        raw = (FIXTURES / "balance_sheet_monthly.csv").read_bytes()
        data = parse_wide_schedule_bytes(raw, "balance_sheet_monthly.csv")
        assert data["Cash"]["2022-01"] == Decimal("2525692.03")
        assert "Total Assets" in data

    def test_excludes_fy_annual_columns(self):
        raw = (FIXTURES / "revenue_schedule.csv").read_bytes()
        data = parse_wide_schedule_bytes(raw, "revenue_schedule.csv")
        periods = data["4001"].keys()
        assert all(len(p) == 7 for p in periods)  # "YYYY-MM", not "FY2022"


class TestPeriodRowScheduleParser:
    def test_parses_working_capital_schedule(self):
        raw = (FIXTURES / "working_capital_schedule.csv").read_bytes()
        data = parse_period_row_schedule_bytes(raw, "working_capital_schedule.csv")
        assert data["AR"]["2022-01"] == Decimal("1408828.88")
        assert data["NWC"]["2022-01"] == Decimal("1686285.67")


class TestDebtScheduleParser:
    def test_groups_by_lender_and_uses_latest_period(self):
        raw = (FIXTURES / "debt_schedule.csv").read_bytes()
        instruments = parse_debt_schedule_bytes(raw, "debt_schedule.csv", "test-deal")
        assert len(instruments) == 1
        inst = instruments[0]
        assert inst.lender == "First Midwest Bank"
        assert inst.facility_type == "revolver"
        assert inst.principal_outstanding == Decimal("12491485.67")
        assert inst.interest_rate_pct == Decimal("1.45")
        assert inst.maturity_date.isoformat() == "2027-12-31"
        assert inst.extraction_confidence == 1.0
        assert inst.source_document == "debt_schedule.csv"


class TestSupportingScheduleParser:
    def test_parses_rows_preserving_columns(self):
        raw = (FIXTURES / "fixed_asset_register.csv").read_bytes()
        rows = parse_supporting_schedule_bytes(raw, "fixed_asset_register.csv")
        assert len(rows) == 5
        assert "Asset ID" in rows[0]
        assert "Net Book Value" in rows[0]


class TestReconcileSchedules:
    def _pnl(self, revenue: Decimal, pk: str = "2024-01") -> PnLStatement:
        from datetime import date
        return PnLStatement(
            deal_id="d", periods=[date(2024, 1, 1)], rows=[],
            revenue={pk: revenue}, gross_profit={pk: revenue}, ebitda={pk: revenue},
            ebit={pk: revenue}, net_income={pk: revenue},
            gross_margin={pk: 1.0}, ebitda_margin={pk: 1.0},
        )

    def test_matching_schedule_passes(self):
        pnl = self._pnl(Decimal("1000000"))
        schedule_data = {"income_statement": {"Total Revenue": {"2024-01": "1000000"}}}
        tie_outs = reconcile_schedules(schedule_data, pnl, None, None)
        assert len(tie_outs) == 1
        assert tie_outs[0].status == "Pass"

    def test_mismatched_schedule_fails(self):
        pnl = self._pnl(Decimal("1000000"))
        schedule_data = {"income_statement": {"Total Revenue": {"2024-01": "5000000"}}}
        tie_outs = reconcile_schedules(schedule_data, pnl, None, None)
        assert len(tie_outs) == 1
        assert tie_outs[0].status == "Fail"

    def test_account_level_schedule_excludes_total_row(self):
        """Regression test: revenue/cogs/opex schedules commonly end with a TOTAL row —
        summing it in would double-count against the per-account total."""
        pnl = self._pnl(Decimal("300"))
        schedule_data = {
            "revenue": {
                "4001": {"2024-01": "100"},
                "4002": {"2024-01": "200"},
                "TOTAL": {"2024-01": "300"},
            }
        }
        tie_outs = reconcile_schedules(schedule_data, pnl, None, None)
        assert len(tie_outs) == 1
        assert tie_outs[0].observed == Decimal("300")
        assert tie_outs[0].status == "Pass"

    def test_no_schedules_returns_empty(self):
        assert reconcile_schedules({}, self._pnl(Decimal("1")), None, None) == []

    def test_missing_statement_skips_that_groups_checks(self):
        # schedule present but BS never built (e.g. PnL-only GL export) -> no crash, no tie-outs
        schedule_data = {"balance_sheet": {"Total Assets": {"2024-01": "100"}}}
        assert reconcile_schedules(schedule_data, None, None, None) == []


class TestEndToEndIngestion:
    def _upload(self, deal_id: str, filenames: list[str]) -> None:
        for name in filenames:
            file_store.save_upload(deal_id, name, (FIXTURES / name).read_bytes())

    def test_previously_skipped_files_now_parse(self):
        deal_id = "test-schedule-ingestion-001"
        self._upload(deal_id, [
            "sample_gl.csv", "balance_sheet_monthly.csv", "debt_schedule.csv",
            "sample_payroll_schedule.csv",
        ])

        result = ing_orch.run(deal_id)

        statuses = {r.filename: r.parse_status for r in result.inventory.documents}
        assert statuses["balance_sheet_monthly.csv"] == "parsed"
        assert statuses["debt_schedule.csv"] == "parsed"
        assert statuses["sample_payroll_schedule.csv"] == "parsed"

        types = {r.filename: r.document_type for r in result.inventory.documents}
        assert types["balance_sheet_monthly.csv"] == DocumentType.BALANCE_SHEET_SCHEDULE
        assert types["debt_schedule.csv"] == DocumentType.DEBT_SCHEDULE
        assert types["sample_payroll_schedule.csv"] == DocumentType.PAYROLL_SCHEDULE

        assert result.debt_schedule is not None
        assert len(result.debt_schedule.instruments) == 1
        assert result.debt_schedule.instruments[0].lender == "First Midwest Bank"

        assert result.schedule_reconciliation is not None
        assert "balance_sheet" in result.schedule_reconciliation

        assert result.supporting_schedules is not None
        assert "sample_payroll_schedule.csv" in result.supporting_schedules


class TestContractsAnalyzeSurvivesRerun:
    def _create_deal(self, name: str) -> str:
        resp = client.post("/api/v1/deals", json={
            "company_name": name, "deal_name": f"{name} — Schedule Test", "currency": "USD",
        })
        assert resp.status_code == 201
        return resp.json()["deal_id"]

    def _upload(self, deal_id: str, filenames: list[str]) -> None:
        files = [("files", (fn, open(FIXTURES / fn, "rb"), "application/octet-stream")) for fn in filenames]
        resp = client.post(f"/api/v1/deals/{deal_id}/upload", files=files)
        assert resp.status_code == 200

    def _run_stages(self, deal_id: str, stages: list[str]) -> None:
        resp = client.post(f"/api/v1/deals/{deal_id}/process", json={"stages": stages})
        assert resp.status_code == 200
        for _ in range(60):
            status = client.get(f"/api/v1/deals/{deal_id}/status").json()
            if all(status["stages"].get(s) == "complete" for s in stages):
                return
            if any(status["stages"].get(s) == "failed" for s in stages):
                pytest.fail(f"Pipeline failed: {status.get('error')}")
            time.sleep(0.5)
        pytest.fail("Pipeline timed out")

    def test_csv_debt_instrument_survives_analyze_rerun(self):
        deal_id = self._create_deal("CSV Debt Schedule Test Co")
        self._upload(deal_id, ["sample_gl.csv", "debt_schedule.csv"])
        self._run_stages(deal_id, ["ingestion"])

        first = client.get(f"/api/v1/deals/{deal_id}/contracts")
        assert first.status_code == 200
        assert len(first.json()["instruments"]) == 1
        assert first.json()["instruments"][0]["lender"] == "First Midwest Bank"

        second = client.post(f"/api/v1/deals/{deal_id}/contracts/analyze")
        assert second.status_code == 200
        assert len(second.json()["instruments"]) == 1
        assert second.json()["instruments"][0]["lender"] == "First Midwest Bank"
