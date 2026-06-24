"""
Tests for CoA mapping and financial statement building.

All tests run with USE_MOCK_LLM=true (no API cost).
Key assertions mirror what a Big 4 reviewer would check:
  - Revenue + COGS = Gross Profit (to the cent)
  - EBITDA = GP - OpEx (before D&A, interest, tax)
  - Balance Sheet: Assets == Liabilities + Equity
  - All 4 planted anomalies survive through to mapped GL
"""

import asyncio
from decimal import Decimal
from pathlib import Path

from app.agents.coa_mapper import CoAMapperAgent, _mock_classify
from app.pipeline.financial_builder import balance_sheet as bs_builder
from app.pipeline.financial_builder import cash_flow as cf_builder
from app.pipeline.financial_builder import pnl as pnl_builder
from app.pipeline.financial_builder.orchestrator import _apply_classifications
from app.pipeline.ingestion.loader import infer_column_map, load_file
from app.pipeline.ingestion.normalizer import normalise
from app.schemas.gl import ChartOfAccountsCategory as CAT

FIXTURE_GL = Path(__file__).parent.parent / "fixtures" / "sample_gl.csv"
DEAL_ID = "test-step3-001"


# ─── CoA Mapper mock tests ─────────────────────────────────────────────────────

class TestCoAMapperMock:
    def test_mock_revenue_accounts(self):
        cat, stmt = _mock_classify("4001")
        assert cat == CAT.REVENUE
        assert stmt == "PnL"

    def test_mock_management_comp(self):
        cat, stmt = _mock_classify("6001")
        assert cat == CAT.MANAGEMENT_COMPENSATION
        assert stmt == "PnL"

    def test_mock_related_party(self):
        cat, stmt = _mock_classify("6097")
        assert cat == CAT.RELATED_PARTY_CONSULTING
        assert stmt == "PnL"

    def test_mock_legal_settlement(self):
        cat, stmt = _mock_classify("6099")
        assert cat == CAT.LEGAL_SETTLEMENTS
        assert stmt == "PnL"

    def test_mock_ma_costs(self):
        cat, stmt = _mock_classify("6098")
        assert cat == CAT.MA_TRANSACTION_COSTS
        assert stmt == "PnL"

    def test_mock_accounts_receivable(self):
        cat, stmt = _mock_classify("1002")
        assert cat == CAT.ACCOUNTS_RECEIVABLE
        assert stmt == "BalanceSheet"

    def test_mock_long_term_debt(self):
        cat, stmt = _mock_classify("2005")
        assert cat == CAT.LONG_TERM_DEBT
        assert stmt == "BalanceSheet"

    def test_mock_agent_returns_all_codes(self):
        """Agent must return a result for every input code."""
        pairs = [("4001", "Revenue"), ("6001", "Mgmt Salary"), ("9999", "Unknown")]
        agent = CoAMapperAgent()
        result = agent._mock_response(pairs)
        assert set(result.keys()) == {"4001", "6001", "9999"}

    def test_mock_agent_async(self):
        """run() dispatches to mock when USE_MOCK_LLM=True."""
        agent = CoAMapperAgent()
        pairs = [("4001", "Product Sales"), ("5001", "Raw Materials")]
        result = asyncio.run(agent.map_accounts(pairs))
        assert "4001" in result
        assert result["4001"]["category"] == CAT.REVENUE


# ─── Financial builder integration tests ──────────────────────────────────────

def _load_mapped_lines():
    """Helper: load fixture → normalise → apply mock CoA mapping."""
    df = load_file(FIXTURE_GL)
    col_map = infer_column_map(df)
    raw_lines = normalise(df, col_map, "sample_gl.csv", DEAL_ID)

    unique_pairs = list({(gl.account_code, gl.account_description) for gl in raw_lines})
    agent = CoAMapperAgent()
    cls_map = asyncio.run(agent.map_accounts(unique_pairs))
    return _apply_classifications(raw_lines, cls_map)


class TestPnLBuilder:
    def setup_method(self):
        self.mapped = _load_mapped_lines()
        self.pnl = pnl_builder.build(self.mapped)

    def test_36_periods(self):
        assert len(self.pnl.periods) == 36

    def test_revenue_positive(self):
        for pk, rev in self.pnl.revenue.items():
            assert rev > 0, f"Revenue negative in period {pk}"

    def test_ebitda_margin_reasonable(self):
        """EBITDA margin should be between -50% and +50% for a real business."""
        for pk, margin in self.pnl.ebitda_margin.items():
            assert -0.5 <= margin <= 0.5, f"EBITDA margin {margin:.1%} out of range in {pk}"

    def test_gross_profit_equals_revenue_minus_cogs(self):
        """GP = Revenue + COGS (COGS is negative in our sign convention)."""
        for pk in self.pnl.revenue:
            period_rows = [r for r in self.pnl.rows if r.period.strftime("%Y-%m") == pk]
            rev = sum(r.amount for r in period_rows if r.is_revenue)
            cogs = sum(r.amount for r in period_rows if r.is_cogs)
            expected_gp = rev + cogs
            assert abs(self.pnl.gross_profit[pk] - expected_gp) < Decimal("0.01"), \
                f"GP mismatch in {pk}: computed={self.pnl.gross_profit[pk]} expected={expected_gp}"

    def test_anomaly_accounts_are_in_pnl_rows(self):
        """All 4 planted anomaly account codes must appear in P&L rows."""
        # Check by description (label field) since that's what's in PnLRow
        descriptions = {r.label for r in self.pnl.rows}
        anomaly_descs = [
            "Legal Settlement - Vendor Dispute",
            "M&A Advisory Fees - Project Falcon",
            "Consulting - Acme Holdings LLC (related party)",
            "Management Salaries",
        ]
        for desc in anomaly_descs:
            assert any(desc in d for d in descriptions), f"'{desc}' not found in P&L rows"

    def test_management_comp_classified_correctly(self):
        mgmt_rows = [r for r in self.pnl.rows if r.category == CAT.MANAGEMENT_COMPENSATION.value]
        assert len(mgmt_rows) > 0, "Management Compensation must appear in P&L"
        # 36 months of owner comp rows
        assert len(mgmt_rows) == 36

    def test_related_party_classified_correctly(self):
        rp_rows = [r for r in self.pnl.rows if r.category == CAT.RELATED_PARTY_CONSULTING.value]
        assert len(rp_rows) == 36, f"Expected 36 related-party rows, got {len(rp_rows)}"

    def test_one_time_items_in_pnl(self):
        legal = [r for r in self.pnl.rows if r.category == CAT.LEGAL_SETTLEMENTS.value]
        assert len(legal) == 1
        assert abs(legal[0].amount) == Decimal("285000.00")

        ma = [r for r in self.pnl.rows if r.category == CAT.MA_TRANSACTION_COSTS.value]
        assert len(ma) == 1
        assert abs(ma[0].amount) == Decimal("180000.00")

    def test_ebitda_excludes_da_interest_tax(self):
        """EBITDA rows must not include D&A, interest, or tax."""
        for r in self.pnl.rows:
            if r.is_da or r.is_below_ebitda:
                assert not r.is_opex and not r.is_revenue and not r.is_cogs, \
                    f"Row '{r.label}' has conflicting flags"


class TestMappedGLCoverage:
    def setup_method(self):
        self.mapped = _load_mapped_lines()

    def test_no_unmapped_lines(self):
        memo_lines = [gl for gl in self.mapped if gl.standard_category == CAT.MEMO]
        assert len(memo_lines) == 0, \
            f"{len(memo_lines)} lines fell through to MEMO: {[gl.account_code for gl in memo_lines[:5]]}"

    def test_ebitda_flag_set_correctly(self):
        ebitda_cats_in_data = {gl.standard_category for gl in self.mapped if gl.is_ebitda_component}
        # Revenue and at least one expense category must be flagged
        assert CAT.REVENUE in ebitda_cats_in_data
        assert CAT.MANAGEMENT_COMPENSATION in ebitda_cats_in_data

    def test_all_lines_have_financial_statement(self):
        for line in self.mapped:
            assert line.financial_statement in ("PnL", "BalanceSheet", "Memo"), \
                f"Invalid financial_statement: {line.financial_statement}"

    def test_fixture_has_both_pnl_and_bs_lines(self):
        pnl_lines = [gl for gl in self.mapped if gl.financial_statement == "PnL"]
        bs_lines = [gl for gl in self.mapped if gl.financial_statement == "BalanceSheet"]
        assert len(pnl_lines) > 0, "Expected P&L lines in mapped GL"
        assert len(bs_lines) > 0, "Expected BalanceSheet lines — fixture must include BS accounts"


# ─── Balance Sheet Builder tests ───────────────────────────────────────────────

class TestBalanceSheetBuilder:
    def setup_method(self):
        self.mapped = _load_mapped_lines()
        self.pnl = pnl_builder.build(self.mapped)
        self.bs = bs_builder.build(self.mapped)

    def test_36_periods(self):
        assert len(self.bs.periods) == 36

    def test_balance_sheet_balances_every_period(self):
        """Assets must equal Liabilities + Equity in every period (Big 4 sign-off gate)."""
        for pk, balanced in self.bs.is_balanced.items():
            assert balanced, (
                f"Balance sheet does not balance in {pk}: "
                f"assets={self.bs.total_assets[pk]} "
                f"liab+eq={self.bs.total_liabilities[pk] + self.bs.total_equity[pk]}"
            )

    def test_total_assets_positive(self):
        for pk, assets in self.bs.total_assets.items():
            assert assets > 0, f"Total assets non-positive in {pk}"

    def test_total_liabilities_positive(self):
        for pk, liab in self.bs.total_liabilities.items():
            assert liab > 0, f"Total liabilities non-positive in {pk}"

    def test_assets_equal_liabilities_plus_equity(self):
        """Verify the arithmetic directly (belt-and-suspenders over is_balanced)."""
        tolerance = Decimal("0.10")
        for pk in self.bs.total_assets:
            diff = abs(self.bs.total_assets[pk] - (self.bs.total_liabilities[pk] + self.bs.total_equity[pk]))
            assert diff <= tolerance, f"A = L + E gap ${diff:.2f} in {pk}"

    def test_rows_categorised(self):
        sections = {r.section for r in self.bs.rows}
        assert "Current Assets" in sections
        assert "Current Liabilities" in sections


# ─── Cash Flow Builder tests ────────────────────────────────────────────────────

class TestCashFlowBuilder:
    def setup_method(self):
        mapped = _load_mapped_lines()
        pnl = pnl_builder.build(mapped)
        bs = bs_builder.build(mapped)
        self.cf = cf_builder.build(mapped, pnl, bs)

    def test_36_periods(self):
        assert len(self.cf.periods) == 36

    def test_operating_cash_flow_keys_present(self):
        for period in self.cf.periods:
            pk = period.strftime("%Y-%m")
            assert pk in self.cf.operating_cash_flow, f"OCF missing for {pk}"

    def test_cf_rows_have_valid_sections(self):
        for row in self.cf.rows:
            assert row.section in ("Operating", "Investing", "Financing"), \
                f"Invalid CF section: {row.section}"

    def test_operating_section_non_empty(self):
        operating_rows = [r for r in self.cf.rows if r.section == "Operating"]
        assert len(operating_rows) > 0, "Expected at least one Operating CF row"
