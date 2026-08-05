"""Databook generator tests."""

from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.config import settings
from app.pipeline.databook.generator import DatabookError, generate
from app.storage import deal_store, file_store
from app.storage.json_io import write_json_encrypted

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def deal_with_qoe(tmp_path):
    deal = deal_store.create_deal("Databook Co", "Export Test", "USD")
    deal_id = deal["deal_id"]
    processed = file_store.get_processed_dir(deal_id)

    qoe_report = {
        "deal_id": deal_id,
        "waterfall": [
            {"label": "Reported EBITDA", "amount": "5000000", "type": "base"},
            {"label": "Owner Comp Add-back", "amount": "200000", "type": "addback"},
            {"label": "Adjusted EBITDA", "amount": "5200000", "type": "result"},
        ],
        "adjustments": [
            {
                "adjustment_id": "ADJ-001",
                "label": "Owner Comp Normalisation",
                "category": "Owner/Related Party",
                "direction": "add_back",
                "adjustment_amount": "200000",
                "source_gl_line_ids": ["GL-ABC123"],
            }
        ],
    }
    write_json_encrypted(processed / "qoe_report.json", qoe_report)

    return deal_id


@pytest.fixture
def deal_with_all_reports(deal_with_qoe):
    """Adds NWC, Net Debt, DCF, Commercial Health, Contracts, and Narrative
    reports on top of the QoE-only fixture, so the databook's optional sheets
    for each of those have real data to render instead of being omitted."""
    deal_id = deal_with_qoe
    processed = file_store.get_processed_dir(deal_id)

    write_json_encrypted(processed / "nwc_report.json", {
        "deal_id": deal_id, "status": "complete", "message": "ok",
        "has_ar_aging": True, "has_ap_aging": True,
        "data_points": [{
            "period": "2024-12-01", "accounts_receivable": "100000", "inventory": "50000",
            "prepaid_expenses": "5000", "other_current_assets": "0", "accounts_payable": "60000",
            "accrued_liabilities": "10000", "deferred_revenue": "0", "current_debt": "20000",
            "other_current_liabilities": "0", "net_working_capital": "65000", "nwc_as_pct_revenue": 0.1,
        }],
        "pegs": [{
            "method": "ltm_average", "peg_amount": "65000", "confidence_interval_low": "60000",
            "confidence_interval_high": "70000", "seasonality_detected": False,
            "recommended": True, "rationale": "Simple trailing average.",
        }],
        "peak_nwc": "70000", "peak_period": "2024-12", "trough_nwc": "60000", "trough_period": "2024-01",
        "nwc_volatility": 0.05,
        "ratios": {"period": "2024-12", "dso_days": 30.0, "dpo_days": 25.0, "dio_days": 20.0,
                   "cash_conversion_cycle_days": 25.0, "ar_over_60d_pct": 5.0, "ap_over_60d_pct": 3.0},
    })

    write_json_encrypted(processed / "net_debt_report.json", {
        "deal_id": deal_id, "status": "complete", "message": "ok", "period": "2024-12",
        "cash_and_equivalents": "300000", "current_debt": "20000", "long_term_debt": "480000",
        "total_debt": "500000", "net_debt": "200000", "net_debt_to_ebitda": 0.2,
        "bridge": [
            {"label": "Total Debt", "amount": "500000", "is_subtotal": True},
            {"label": "Less: Cash", "amount": "-300000", "is_subtotal": False},
            {"label": "Net Debt", "amount": "200000", "is_subtotal": True},
        ],
        "instruments": [{
            "instrument_id": "INST-1", "facility_type": "term_loan", "lender": "Acme Bank",
            "principal_outstanding": "500000", "interest_rate_pct": "6.5",
            "maturity_date": "2028-01-01", "source_document": "debt_schedule.csv",
            "extraction_confidence": 0.9,
        }],
        "instrument_principal_total": "500000", "reconciliation_variance": "0",
        "reconciliation_note": "Matches GL within tolerance.",
    })

    write_json_encrypted(processed / "dcf_report.json", {
        "deal_id": deal_id, "status": "complete", "message": "ok", "projection_periods": 3,
        "assumptions": {"discount_rate_annual": 0.12, "terminal_growth_rate_annual": 0.02},
        "projected_fcf": {"2025-01": "65000", "2025-02": "70000", "2025-03": "80000"},
        "pv_of_fcf": {"2025-01": "64389.03", "2025-02": "68690.24", "2025-03": "77765.23"},
        "sum_pv_of_fcf": "210844.50", "terminal_value": "4000000",
        "pv_of_terminal_value": "3800000", "enterprise_value": "4010844.50",
        "limitations": ["Unlevered FCF approximated as EBITDA - Capex, no tax/NWC adjustment."],
    })

    write_json_encrypted(processed / "commercial_report.json", {
        "deal_id": deal_id, "status": "partial",
        "message": "Growth, margin, and volatility metrics computed from ingested financials.",
        "revenue_growth_yoy_pct": {"2023": 8.5, "2024": 6.2},
        "gross_margin_trend_pct": {"2024-11": 43.1, "2024-12": 43.2},
        "ebitda_margin_trend_pct": {"2024-11": 18.0, "2024-12": 18.2},
        "revenue_volatility": 0.06, "seasonality_detected": False,
        "seasonality_note": "Q4 revenue within normal range.",
        "unavailable_metrics": ["customer_concentration_pct (requires customer-level revenue schedule)"],
    })

    write_json_encrypted(processed / "contract_analysis.json", {
        "deal_id": deal_id, "status": "complete", "message": "ok",
        "instruments": [{
            "instrument_id": "INST-1", "deal_id": deal_id, "facility_type": "term_loan",
            "lender": "Acme Bank", "principal_outstanding": "500000", "interest_rate_pct": "6.5",
            "maturity_date": "2028-01-01", "covenants_summary": "Max leverage 3.5x EBITDA.",
            "change_of_control_clause": "Requires lender consent.",
            "prepayment_terms": "No penalty after year 2.", "events_of_default": "Standard.",
            "material_obligations": ["Quarterly financial reporting"],
            "source_document": "credit_agreement.pdf", "extraction_confidence": 0.92,
        }],
        "clauses": [{
            "clause_type": "change_of_control", "summary": "Lender consent required on COC.",
            "source_document": "credit_agreement.pdf", "instrument_id": "INST-1", "confidence": 0.92,
        }],
        "extraction_warnings": [],
    })

    write_json_encrypted(processed / "narrative_report.json", {
        "deal_id": deal_id, "status": "complete", "message": "ok",
        "generated_at": "2026-01-01T00:00:00Z",
        "sections": [
            {
                "section_id": "executive_summary",
                "title": "Executive Summary",
                "content": "The company shows steady growth.",
            },
        ],
        "figures_used": {"ltm_revenue": "63700000"},
        "data_gaps": [],
    })

    return deal_id


class TestDatabookGenerator:
    def test_raises_without_qoe(self):
        deal = deal_store.create_deal("No QoE", "Fail Test", "USD")
        with pytest.raises(DatabookError, match="QoE report not found"):
            generate(deal["deal_id"])

    def test_generates_valid_xlsx(self, deal_with_qoe):
        content = generate(deal_with_qoe)
        assert content[:2] == b"PK"  # ZIP/XLSX magic

        out = settings.processed_dir / deal_with_qoe / "test_databook.xlsx"
        out.write_bytes(content)
        wb = load_workbook(out)
        assert "Cover" in wb.sheetnames
        assert "QoE Waterfall" in wb.sheetnames
        assert "IRL" in wb.sheetnames

    def test_generates_all_optional_sheets_when_reports_exist(self, deal_with_all_reports):
        content = generate(deal_with_all_reports)
        out = settings.processed_dir / deal_with_all_reports / "test_databook_full.xlsx"
        out.write_bytes(content)
        wb = load_workbook(out)

        for sheet_name in [
            "NWC Trend", "NWC Pegs", "Net Debt", "Debt Instruments",
            "DCF", "Commercial Health", "Contracts", "Narrative",
        ]:
            assert sheet_name in wb.sheetnames, f"missing sheet: {sheet_name}"

        nwc_sheet = wb["NWC Trend"]
        assert nwc_sheet.cell(row=2, column=1).value == "2024-12-01"
        assert nwc_sheet.cell(row=2, column=11).value == "65000"  # NWC column

        dcf_sheet = wb["DCF"]
        dcf_values = [dcf_sheet.cell(row=r, column=1).value for r in range(1, dcf_sheet.max_row + 1)]
        assert "Enterprise value" in dcf_values

        narrative_sheet = wb["Narrative"]
        assert narrative_sheet.cell(row=2, column=1).value == "Executive Summary"
        assert "steady growth" in narrative_sheet.cell(row=2, column=2).value

    def test_omits_optional_sheets_when_reports_missing(self, deal_with_qoe):
        # deal_with_qoe only has qoe_report.json — every optional sheet below
        # should be cleanly skipped (with a logged warning), not error.
        content = generate(deal_with_qoe)
        out = settings.processed_dir / deal_with_qoe / "test_databook_partial.xlsx"
        out.write_bytes(content)
        wb = load_workbook(out)

        for sheet_name in [
            "NWC Trend", "NWC Pegs", "Net Debt", "Debt Instruments",
            "DCF", "Commercial Health", "Contracts", "Narrative",
        ]:
            assert sheet_name not in wb.sheetnames

    def test_api_export(self, deal_with_qoe):
        from fastapi.testclient import TestClient

        from app.main import app
        from tests.auth_helpers import authenticate

        client = TestClient(app)
        user = authenticate(client)
        # deal_with_qoe was created directly via deal_store (not through the API),
        # so it has no owner — stamp it to the authenticated test user so the
        # ownership check in require_deal_owner passes.
        deal_store.update_deal(deal_with_qoe, {"owner_user_id": user["id"]})

        resp = client.post(f"/api/v1/deals/{deal_with_qoe}/databook/export")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]
