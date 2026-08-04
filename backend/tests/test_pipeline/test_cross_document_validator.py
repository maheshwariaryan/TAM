"""
Unit tests for the deal-configurable tie-out tolerance (Slice 3 — Settings wiring).
validate_cross_documents/reconcile_schedules used to hard-code separate AR (0.5%),
AP (1.0%), and schedule (1.0%) tolerance constants; now all three take a single
`tolerance_pct` collapsed from app.schemas.settings.DealSettings.tie_out_tolerance_pct,
falling back to the prior AR-equivalent default (0.5%) when not passed.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.pipeline.ingestion.cross_document_validator import (
    reconcile_schedules,
    validate_cross_documents,
)
from app.schemas.aging import AgingReport, AgingSummary
from app.schemas.financials import PnLStatement

pytestmark = pytest.mark.unit


def _ar_report(total: Decimal) -> AgingReport:
    return AgingReport(
        deal_id="d",
        document_type="ar_aging",
        summaries=[
            AgingSummary(
                deal_id="d", document_type="ar_aging", period=date(2024, 1, 1),
                bucket_0_30=total, bucket_31_60=Decimal("0"), bucket_61_90=Decimal("0"),
                bucket_90_plus=Decimal("0"), total=total,
                source_file="ar_aging.csv", source_row=1,
            )
        ],
    )


class _Line:
    def __init__(self, account_code: str, amount: Decimal, period: date):
        self.account_code = account_code
        self.amount = amount
        self.period = period


class TestValidateCrossDocumentsTolerance:
    def _gl_lines(self, amount: Decimal) -> list:
        return [_Line("1002-AR", amount, date(2024, 1, 1))]

    def test_default_tolerance_fails_on_2pct_variance(self):
        """2% variance exceeds the default 0.5% AR tolerance (>2x -> Fail)."""
        result = validate_cross_documents(
            "d", self._gl_lines(Decimal("102000")), _ar_report(Decimal("100000")), None,
        )
        assert result.tie_outs[0].status == "Fail"

    def test_wider_deal_tolerance_turns_the_same_variance_into_a_pass(self):
        """The exact same 2% variance passes once the deal's configured tolerance is
        widened to 3% — proves tolerance_pct actually drives Pass/Fail, not just saves."""
        result = validate_cross_documents(
            "d", self._gl_lines(Decimal("102000")), _ar_report(Decimal("100000")), None,
            tolerance_pct=3.0,
        )
        assert result.tie_outs[0].status == "Pass"

    def test_none_falls_back_to_prior_default(self):
        default_result = validate_cross_documents(
            "d", self._gl_lines(Decimal("102000")), _ar_report(Decimal("100000")), None,
        )
        explicit_result = validate_cross_documents(
            "d", self._gl_lines(Decimal("102000")), _ar_report(Decimal("100000")), None,
            tolerance_pct=0.5,
        )
        assert default_result.tie_outs[0].status == explicit_result.tie_outs[0].status
        assert default_result.tie_outs[0].tolerance_pct == explicit_result.tie_outs[0].tolerance_pct == 0.5


class TestReconcileSchedulesTolerance:
    def _pnl(self, revenue: Decimal, pk: str = "2024-01") -> PnLStatement:
        return PnLStatement(
            deal_id="d", periods=[date(2024, 1, 1)], rows=[],
            revenue={pk: revenue}, gross_profit={pk: revenue}, ebitda={pk: revenue},
            ebit={pk: revenue}, net_income={pk: revenue},
            gross_margin={pk: 1.0}, ebitda_margin={pk: 1.0},
        )

    def test_default_tolerance_fails_on_3pct_variance(self):
        """3% variance exceeds 2x the default 1.0% schedule tolerance -> Fail."""
        pnl = self._pnl(Decimal("1000000"))
        schedule_data = {"income_statement": {"Total Revenue": {"2024-01": "1030000"}}}
        tie_outs = reconcile_schedules(schedule_data, pnl, None, None)
        assert tie_outs[0].status == "Fail"

    def test_deal_tolerance_widens_the_same_variance_to_a_pass(self):
        pnl = self._pnl(Decimal("1000000"))
        schedule_data = {"income_statement": {"Total Revenue": {"2024-01": "1030000"}}}
        tie_outs = reconcile_schedules(schedule_data, pnl, None, None, tolerance_pct=5.0)
        assert tie_outs[0].status == "Pass"
