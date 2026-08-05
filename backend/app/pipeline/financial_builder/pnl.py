"""
P&L Builder — constructs the income statement from mapped GL lines.

Strictly deterministic: pure Pandas aggregation, zero LLM calls.
All amounts use Decimal to prevent floating-point errors in financial totals.

Sign convention (economic):
  Revenue / income lines  → stored as NEGATIVE in GL (credit-normal)
                          → presented as POSITIVE in P&L (as revenue)
  Expense lines           → stored as POSITIVE in GL (debit-normal)
                          → presented as NEGATIVE in P&L (reduces income)

EBITDA = Revenue - COGS - Operating Expenses (before D&A, interest, tax)
"""

import logging
from collections import defaultdict
from decimal import Decimal

from app.schemas.financials import PnLRow, PnLStatement
from app.schemas.gl import (
    EBITDA_COMPONENTS,
    MappedGLLine,
)
from app.schemas.gl import (
    ChartOfAccountsCategory as CAT,
)

logger = logging.getLogger(__name__)

# Categories that are revenue (credit-normal → flip sign for P&L presentation)
_REVENUE_CATS = {CAT.REVENUE, CAT.OTHER_INCOME}

# Categories counted as COGS
_COGS_CATS = {
    CAT.COST_OF_GOODS_SOLD,
    CAT.DIRECT_LABOUR,
    CAT.MANUFACTURING_OVERHEAD,
    CAT.FREIGHT_IN,
}

# D&A — excluded from EBITDA but included in EBIT
_DA_CATS = {CAT.DEPRECIATION, CAT.AMORTISATION}

# Below EBITDA — interest, tax
_BELOW_EBITDA_CATS = {CAT.INTEREST_EXPENSE, CAT.INTEREST_INCOME, CAT.INCOME_TAX}

# All opex = EBITDA components minus revenue and COGS
_OPEX_CATS = EBITDA_COMPONENTS - _REVENUE_CATS - _COGS_CATS


def build(lines: list[MappedGLLine]) -> PnLStatement:
    """
    Build a PnLStatement from a list of mapped GL lines.
    Only PnL-statement lines are processed; BalanceSheet lines are ignored.
    """
    pnl_lines = [gl for gl in lines if gl.financial_statement == "PnL"]
    if not pnl_lines:
        raise ValueError("No PnL lines found in mapped GL. Verify CoA mapping completed.")

    deal_id = pnl_lines[0].deal_id
    periods = sorted({gl.period for gl in pnl_lines})

    # Aggregate amounts by (period, category, description)
    # Key: (period, account_code, account_description, category)
    agg: dict[tuple, Decimal] = defaultdict(Decimal)
    for line in pnl_lines:
        key = (line.period, line.account_code, line.account_description, line.standard_category)
        agg[key] += line.amount

    rows: list[PnLRow] = []
    for (period, code, desc, cat), amount in sorted(agg.items()):
        is_rev = cat in _REVENUE_CATS
        # Flip sign for P&L presentation: revenue is positive, expenses negative
        pnl_amount = -amount if is_rev else -amount
        # Actually: GL debit = positive, GL credit = negative
        # Revenue is credit-normal → GL amount is negative → negate = positive in P&L ✓
        # Expense is debit-normal → GL amount is positive → negate = negative in P&L ✓

        rows.append(PnLRow(
            period=period,
            category=cat.value,
            label=desc,
            amount=pnl_amount,
            is_revenue=is_rev,
            is_cogs=cat in _COGS_CATS,
            is_opex=cat in _OPEX_CATS,
            is_da=cat in _DA_CATS,
            is_below_ebitda=cat in _BELOW_EBITDA_CATS,
        ))

    # Build summary lines per period
    revenue: dict[str, Decimal] = {}
    gross_profit: dict[str, Decimal] = {}
    ebitda: dict[str, Decimal] = {}
    ebit: dict[str, Decimal] = {}
    net_income: dict[str, Decimal] = {}
    gross_margin: dict[str, float] = {}
    ebitda_margin: dict[str, float] = {}

    for period in periods:
        pk = period.strftime("%Y-%m")
        period_rows = [r for r in rows if r.period == period]

        rev = sum((r.amount for r in period_rows if r.is_revenue), Decimal("0"))
        cogs = sum((r.amount for r in period_rows if r.is_cogs), Decimal("0"))
        opex = sum((r.amount for r in period_rows if r.is_opex), Decimal("0"))
        da = sum((r.amount for r in period_rows if r.is_da), Decimal("0"))
        below = sum((r.amount for r in period_rows if r.is_below_ebitda), Decimal("0"))

        gp = rev + cogs          # cogs is negative, so this is rev - |cogs|
        ebitda_val = gp + opex   # opex is negative
        ebit_val = ebitda_val + da
        ni = ebit_val + below

        revenue[pk] = rev
        gross_profit[pk] = gp
        ebitda[pk] = ebitda_val
        ebit[pk] = ebit_val
        net_income[pk] = ni

        gross_margin[pk] = float(gp / rev) if rev else 0.0
        ebitda_margin[pk] = float(ebitda_val / rev) if rev else 0.0

    logger.info(
        "P&L built for deal %s: %d rows across %d periods",
        deal_id, len(rows), len(periods),
    )

    return PnLStatement(
        deal_id=deal_id,
        periods=periods,
        rows=rows,
        revenue=revenue,
        gross_profit=gross_profit,
        ebitda=ebitda,
        ebit=ebit,
        net_income=net_income,
        gross_margin=gross_margin,
        ebitda_margin=ebitda_margin,
    )
