"""
Balance Sheet Builder — reconstructs the balance sheet from mapped GL lines.

For each period, aggregates BalanceSheet-tagged GL lines into the standard sections.
Cross-checks: Total Assets must equal Total Liabilities + Equity (within $0.05 tolerance).

Sign convention in the output (presentation, not GL):
  Assets       → Positive (debit-normal; GL amount is already positive)
  Liabilities  → Positive (credit-normal; GL amount is negative → negate for presentation)
  Equity       → Positive (credit-normal; negate for presentation)
"""

import logging
from collections import defaultdict
from decimal import Decimal
from typing import Literal

from app.schemas.financials import BalanceSheet, BalanceSheetRow
from app.schemas.gl import ChartOfAccountsCategory as CAT
from app.schemas.gl import MappedGLLine

logger = logging.getLogger(__name__)

_BALANCE_TOLERANCE = Decimal("0.05")

# Map category → section
_SECTION_MAP: dict[CAT, Literal[
    "Current Assets", "Non-Current Assets",
    "Current Liabilities", "Non-Current Liabilities", "Equity"
]] = {
    CAT.CASH:                        "Current Assets",
    CAT.ACCOUNTS_RECEIVABLE:         "Current Assets",
    CAT.INVENTORY:                   "Current Assets",
    CAT.PREPAID_EXPENSES:            "Current Assets",
    CAT.OTHER_CURRENT_ASSETS:        "Current Assets",

    CAT.FIXED_ASSETS:                "Non-Current Assets",
    CAT.ACCUMULATED_DEPRECIATION:    "Non-Current Assets",
    CAT.INTANGIBLES:                 "Non-Current Assets",
    CAT.OTHER_NON_CURRENT_ASSETS:    "Non-Current Assets",

    CAT.ACCOUNTS_PAYABLE:            "Current Liabilities",
    CAT.ACCRUED_LIABILITIES:         "Current Liabilities",
    CAT.DEFERRED_REVENUE:            "Current Liabilities",
    CAT.CURRENT_DEBT:                "Current Liabilities",
    CAT.OTHER_CURRENT_LIABILITIES:   "Current Liabilities",

    CAT.LONG_TERM_DEBT:              "Non-Current Liabilities",
    CAT.DEFERRED_TAX:                "Non-Current Liabilities",
    CAT.OTHER_NON_CURRENT_LIABILITIES: "Non-Current Liabilities",

    CAT.SHARE_CAPITAL:               "Equity",
    CAT.RETAINED_EARNINGS:           "Equity",
    CAT.OWNER_DISTRIBUTIONS:         "Equity",
    CAT.OTHER_EQUITY:                "Equity",
}

_ASSET_SECTIONS = {"Current Assets", "Non-Current Assets"}
_LIABILITY_SECTIONS = {"Current Liabilities", "Non-Current Liabilities"}


def build(lines: list[MappedGLLine]) -> BalanceSheet:
    bs_lines = [gl for gl in lines if gl.financial_statement == "BalanceSheet"]
    if not bs_lines:
        raise ValueError(
            "No BalanceSheet lines in mapped GL. "
            "If this is a P&L-only upload, balance sheet analysis is unavailable."
        )

    deal_id = bs_lines[0].deal_id
    periods = sorted({gl.period for gl in bs_lines})

    # Aggregate by (period, account_code, description, category)
    agg: dict[tuple, Decimal] = defaultdict(Decimal)
    for line in bs_lines:
        key = (line.period, line.account_code, line.account_description, line.standard_category)
        agg[key] += line.amount

    rows: list[BalanceSheetRow] = []
    for (period, code, desc, cat), gl_amount in sorted(agg.items()):
        section = _SECTION_MAP.get(cat)
        if section is None:
            logger.debug("Balance sheet category %s has no section mapping — skipping", cat)
            continue

        # Presentation sign:
        #   Assets are debit-normal → GL positive → keep as-is
        #   Liabilities/Equity are credit-normal → GL negative → negate
        if section in _ASSET_SECTIONS:
            amount = gl_amount
        else:
            amount = -gl_amount  # flip to positive for liabilities/equity presentation

        rows.append(BalanceSheetRow(
            period=period,
            category=cat.value,
            label=desc,
            amount=amount,
            section=section,
        ))

    # Summary per period
    total_assets: dict[str, Decimal] = {}
    total_liabilities: dict[str, Decimal] = {}
    total_equity: dict[str, Decimal] = {}
    is_balanced: dict[str, bool] = {}

    for period in periods:
        pk = period.strftime("%Y-%m")
        period_rows = [r for r in rows if r.period == period]

        assets = sum((r.amount for r in period_rows if r.section in _ASSET_SECTIONS), Decimal("0"))
        liab = sum((r.amount for r in period_rows if r.section in _LIABILITY_SECTIONS), Decimal("0"))
        equity = sum((r.amount for r in period_rows if r.section == "Equity"), Decimal("0"))

        total_assets[pk] = assets
        total_liabilities[pk] = liab
        total_equity[pk] = equity

        diff = abs(assets - (liab + equity))
        is_balanced[pk] = diff <= _BALANCE_TOLERANCE
        if not is_balanced[pk]:
            logger.warning(
                "Balance sheet does not balance for period %s: assets=%s liab+eq=%s diff=%s",
                pk, assets, liab + equity, diff,
            )

    logger.info(
        "Balance sheet built for deal %s: %d rows across %d periods",
        deal_id, len(rows), len(periods),
    )

    return BalanceSheet(
        deal_id=deal_id,
        periods=periods,
        rows=rows,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        total_equity=total_equity,
        is_balanced=is_balanced,
    )
