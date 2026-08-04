"""
Unit tests for deal-configurable materiality demotion and graduated cash-conversion
severity bands (Slice 3 — Settings wiring). Pure, synthetic inputs — no LLM, no I/O.
"""

from decimal import Decimal

import pytest

from app.pipeline.redflag_detector import rules as rf_rules
from app.schemas.financials import CashFlowStatement, PnLStatement
from app.schemas.qoe import QoEReport
from app.schemas.redflags import RedFlag

pytestmark = pytest.mark.unit

DEAL_ID = "test-settings-redflags"


def _qoe() -> QoEReport:
    return QoEReport(
        deal_id=DEAL_ID, reported_ebitda={}, adjusted_ebitda={},
        ltm_reported=Decimal("0"), ltm_adjusted=Decimal("0"), ltm_adjustment_total=Decimal("0"),
        adjustments=[], waterfall=[], adjustment_count=0, categories_adjusted=[],
    )


def _pnl(revenue: dict[str, Decimal] | None = None) -> PnLStatement:
    revenue = revenue or {}
    return PnLStatement(
        deal_id=DEAL_ID, periods=[], rows=[],
        revenue=revenue, gross_profit={}, ebitda={}, ebit={}, net_income={},
        gross_margin={}, ebitda_margin={},
    )


class TestMaterialityDemotion:
    def _flag(self, severity: str, impact_low: Decimal | None, impact_high: Decimal | None) -> RedFlag:
        return RedFlag(
            flag_id="f1", deal_id=DEAL_ID, severity=severity, category="Cost Structure",
            title="Test Flag", description="A test flag long enough to pass validation checks.",
            financial_impact_low=impact_low, financial_impact_high=impact_high,
            affected_periods=["2024-01"], source="rule_engine", rule_id="TEST_RULE",
        )

    def test_flag_below_materiality_is_demoted_to_informational(self):
        flags = [self._flag("High", Decimal("10000"), Decimal("20000"))]
        demoted = rf_rules._apply_materiality_demotion(DEAL_ID, flags, materiality_threshold=75_000)
        assert demoted[0].severity == "Informational"
        assert "materiality threshold" in demoted[0].description

    def test_flag_at_or_above_materiality_is_untouched(self):
        flags = [self._flag("High", Decimal("80000"), Decimal("100000"))]
        demoted = rf_rules._apply_materiality_demotion(DEAL_ID, flags, materiality_threshold=75_000)
        assert demoted[0].severity == "High"
        assert demoted[0].description == flags[0].description

    def test_flag_straddling_threshold_is_not_demoted(self):
        """Only demote when the FULL range (including the high estimate) is immaterial —
        a flag whose upper bound still clears the threshold stays at its rule severity."""
        flags = [self._flag("High", Decimal("50000"), Decimal("90000"))]
        demoted = rf_rules._apply_materiality_demotion(DEAL_ID, flags, materiality_threshold=75_000)
        assert demoted[0].severity == "High"

    def test_flag_with_no_impact_estimate_is_never_touched(self):
        flags = [self._flag("Medium", None, None)]
        demoted = rf_rules._apply_materiality_demotion(DEAL_ID, flags, materiality_threshold=75_000)
        assert demoted[0].severity == "Medium"

    def test_already_informational_flag_is_left_alone(self):
        flags = [self._flag("Informational", Decimal("1"), Decimal("2"))]
        demoted = rf_rules._apply_materiality_demotion(DEAL_ID, flags, materiality_threshold=75_000)
        assert demoted[0].description == flags[0].description

    def test_detect_all_applies_demotion_only_when_threshold_given(self):
        """materiality_threshold is opt-in: omitting it (as every pre-existing direct
        caller of detect_all does) must leave severities exactly as before."""
        pnl = _pnl()
        qoe = _qoe()
        flags_without = rf_rules.detect_all(deal_id=DEAL_ID, pnl=pnl, mapped_lines=[], qoe=qoe)
        flags_with = rf_rules.detect_all(
            deal_id=DEAL_ID, pnl=pnl, mapped_lines=[], qoe=qoe, materiality_threshold=75_000,
        )
        assert flags_without == flags_with  # no flags fire for empty input either way


class TestGraduatedCashConversion:
    def _cf_pnl(self, conv_pct_by_year: dict[str, float]) -> tuple[CashFlowStatement, PnLStatement]:
        """Two years of monthly data at a flat monthly EBITDA of 10,000, with operating
        cash flow set so the annual OCF/EBITDA ratio equals the given percent for each year."""
        ebitda: dict[str, Decimal] = {}
        op_cf: dict[str, Decimal] = {}
        for yr, conv_pct in conv_pct_by_year.items():
            annual_ebitda = Decimal("120000")  # 10,000 * 12
            annual_op = annual_ebitda * Decimal(str(conv_pct)) / Decimal("100")
            monthly_ebitda = annual_ebitda / 12
            monthly_op = annual_op / 12
            for m in range(1, 13):
                pk = f"{yr}-{m:02d}"
                ebitda[pk] = monthly_ebitda
                op_cf[pk] = monthly_op

        pnl = PnLStatement(
            deal_id=DEAL_ID, periods=[], rows=[],
            revenue={}, gross_profit={}, ebitda=ebitda, ebit={}, net_income={},
            gross_margin={}, ebitda_margin={},
        )
        cf = CashFlowStatement(
            deal_id=DEAL_ID, periods=[], rows=[],
            operating_cash_flow=op_cf, investing_cash_flow={}, financing_cash_flow={},
            net_cash_flow={}, cash_conversion={},
        )
        return cf, pnl

    def test_below_medium_band_is_medium_severity(self):
        cf, pnl = self._cf_pnl({"2023": 55.0, "2024": 50.0})
        flags = rf_rules._rule_low_cash_conversion(DEAL_ID, cf, pnl)
        assert len(flags) == 1
        assert flags[0].severity == "Medium"

    def test_below_high_band_is_high_severity(self):
        cf, pnl = self._cf_pnl({"2023": 25.0, "2024": 20.0})
        flags = rf_rules._rule_low_cash_conversion(DEAL_ID, cf, pnl)
        assert len(flags) == 1
        assert flags[0].severity == "High"
        assert "Critical" not in flags[0].title

    def test_at_or_below_critical_band_is_high_with_critical_language(self):
        cf, pnl = self._cf_pnl({"2023": -10.0, "2024": -5.0})
        flags = rf_rules._rule_low_cash_conversion(DEAL_ID, cf, pnl)
        assert len(flags) == 1
        assert flags[0].severity == "High"
        assert "Critical" in flags[0].title

    def test_custom_deal_bands_change_severity_for_the_same_ratio(self):
        """The exact same 45% conversion ratio is Medium under default bands (medium=60)
        but High once the deal's configured medium/high bands are both tightened below it —
        proves the bands actually drive severity, not just save."""
        cf, pnl = self._cf_pnl({"2023": 45.0, "2024": 45.0})
        default_flags = rf_rules._rule_low_cash_conversion(DEAL_ID, cf, pnl)
        assert default_flags[0].severity == "Medium"

        tightened_flags = rf_rules._rule_low_cash_conversion(
            DEAL_ID, cf, pnl, medium_pct=50.0, high_pct=48.0, critical_pct=0.0,
        )
        assert tightened_flags[0].severity == "High"

    def test_single_low_year_does_not_fire(self):
        cf, pnl = self._cf_pnl({"2023": 55.0, "2024": 65.0})
        flags = rf_rules._rule_low_cash_conversion(DEAL_ID, cf, pnl)
        assert flags == []
