"""
Cash Flow Builder — indirect method statement from mapped GL.

Indirect method:
  Start with Net Income
  + Add back D&A (non-cash)
  +/- Changes in working capital (AR, Inventory, AP, etc.)
  = Operating Cash Flow

  Investing: CapEx (changes in fixed assets before depreciation)
  Financing: Debt drawdowns/repayments, owner distributions

Cash conversion ratio (Operating CF / EBITDA) is a key QoE metric.
Values < 60% for 2+ consecutive years trigger a red flag.
"""

import logging
from collections import defaultdict
from decimal import Decimal

from app.schemas.financials import BalanceSheet, CashFlowRow, CashFlowStatement, PnLStatement
from app.schemas.gl import ChartOfAccountsCategory as CAT
from app.schemas.gl import MappedGLLine

logger = logging.getLogger(__name__)


def build(
    lines: list[MappedGLLine],
    pnl: PnLStatement,
    balance_sheet: BalanceSheet,
) -> CashFlowStatement:
    """
    Build an indirect-method cash flow statement.

    Requires both the P&L (for net income and D&A) and balance sheet
    (for working capital movement calculations).
    """
    deal_id = pnl.deal_id
    periods = pnl.periods

    rows: list[CashFlowRow] = []
    operating_cf: dict[str, Decimal] = {}
    investing_cf: dict[str, Decimal] = {}
    financing_cf: dict[str, Decimal] = {}
    net_cf: dict[str, Decimal] = {}
    cash_conversion: dict[str, float | None] = {}

    bs_rows_by_period: dict[str, list] = defaultdict(list)
    for row in balance_sheet.rows:
        bs_rows_by_period[row.period.strftime("%Y-%m")].append(row)

    sorted_periods = sorted(periods)

    for i, period in enumerate(sorted_periods):
        pk = period.strftime("%Y-%m")
        prev_pk = sorted_periods[i - 1].strftime("%Y-%m") if i > 0 else None

        ni = pnl.net_income.get(pk, Decimal("0"))

        # ── D&A add-back ──────────────────────────────────────────────────────
        period_pnl_rows = [r for r in pnl.rows if r.period == period]
        da = -sum((r.amount for r in period_pnl_rows if r.is_da), Decimal("0"))
        # D&A is presented as negative in P&L (reduces income); add back = negate

        rows.append(CashFlowRow(period=period, label="Net Income", amount=ni, section="Operating"))
        rows.append(CashFlowRow(
            period=period, label="Add: Depreciation & Amortisation", amount=da, section="Operating"
        ))

        # ── Working capital movements ─────────────────────────────────────────
        wc_cats = {
            CAT.ACCOUNTS_RECEIVABLE:  ("(Increase)/Decrease in Accounts Receivable", True),
            CAT.INVENTORY:            ("(Increase)/Decrease in Inventory", True),
            CAT.PREPAID_EXPENSES:     ("(Increase)/Decrease in Prepaid Expenses", True),
            CAT.ACCOUNTS_PAYABLE:     ("Increase/(Decrease) in Accounts Payable", False),
            CAT.ACCRUED_LIABILITIES:  ("Increase/(Decrease) in Accrued Liabilities", False),
            CAT.DEFERRED_REVENUE:     ("Increase/(Decrease) in Deferred Revenue", False),
        }

        wc_total = Decimal("0")
        if prev_pk and prev_pk in bs_rows_by_period:
            current_bs = {r.category: r.amount for r in bs_rows_by_period[pk]}
            prev_bs = {r.category: r.amount for r in bs_rows_by_period[prev_pk]}

            for cat, (label, is_asset) in wc_cats.items():
                cur = current_bs.get(cat.value, Decimal("0"))
                prev = prev_bs.get(cat.value, Decimal("0"))
                change = cur - prev
                # Asset increase = cash outflow (negative); liability increase = inflow (positive)
                cf_impact = -change if is_asset else change
                if cf_impact != 0:
                    rows.append(CashFlowRow(period=period, label=label, amount=cf_impact, section="Operating"))
                    wc_total += cf_impact

        op_cf = ni + da + wc_total
        operating_cf[pk] = op_cf

        # ── Investing: CapEx (change in gross fixed assets) ──────────────────
        current_bs_cat = {r.category: r.amount for r in bs_rows_by_period.get(pk, [])}
        prev_bs_cat = {r.category: r.amount for r in bs_rows_by_period.get(prev_pk, [])} if prev_pk else {}

        gross_ppe_cur = current_bs_cat.get(CAT.FIXED_ASSETS.value, Decimal("0"))
        gross_ppe_prev = prev_bs_cat.get(CAT.FIXED_ASSETS.value, Decimal("0"))
        capex = -(gross_ppe_cur - gross_ppe_prev)  # Increase in PPE = cash outflow
        if capex != 0:
            rows.append(CashFlowRow(period=period, label="Capital Expenditure", amount=capex, section="Investing"))
        investing_cf[pk] = capex

        # ── Financing: debt movements + owner distributions ───────────────────
        debt_cats = [CAT.LONG_TERM_DEBT, CAT.CURRENT_DEBT]
        fin_total = Decimal("0")

        for dcat in debt_cats:
            cur_d = current_bs_cat.get(dcat.value, Decimal("0"))
            prev_d = prev_bs_cat.get(dcat.value, Decimal("0"))
            change = cur_d - prev_d
            if change != 0:
                label = "Debt Drawdown" if change > 0 else "Debt Repayment"
                rows.append(CashFlowRow(period=period, label=label, amount=change, section="Financing"))
                fin_total += change

        dist_cur = current_bs_cat.get(CAT.OWNER_DISTRIBUTIONS.value, Decimal("0"))
        dist_prev = prev_bs_cat.get(CAT.OWNER_DISTRIBUTIONS.value, Decimal("0"))
        dist_change = dist_cur - dist_prev
        if dist_change != 0:
            rows.append(CashFlowRow(
                period=period, label="Owner Distributions", amount=-dist_change, section="Financing"
            ))
            fin_total -= dist_change

        financing_cf[pk] = fin_total
        net_cf[pk] = op_cf + capex + fin_total

        # Cash conversion ratio
        ebitda_val = pnl.ebitda.get(pk, Decimal("0"))
        if ebitda_val and ebitda_val != 0:
            cash_conversion[pk] = float(op_cf / ebitda_val)
        else:
            cash_conversion[pk] = None

    logger.info(
        "Cash flow built for deal %s: %d rows across %d periods",
        deal_id, len(rows), len(sorted_periods),
    )

    return CashFlowStatement(
        deal_id=deal_id,
        periods=periods,
        rows=rows,
        operating_cash_flow=operating_cf,
        investing_cash_flow=investing_cf,
        financing_cash_flow=financing_cf,
        net_cash_flow=net_cf,
        cash_conversion=cash_conversion,
    )
