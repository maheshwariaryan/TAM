"""
Financial statements API — P&L, Balance Sheet, Cash Flow.

GET /api/v1/deals/{deal_id}/financials/pnl
GET /api/v1/deals/{deal_id}/financials/balance-sheet
GET /api/v1/deals/{deal_id}/financials/cash-flow
GET /api/v1/deals/{deal_id}/financials/summary
"""

import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.schemas.financials import BalanceSheet, CashFlowStatement, PnLRow, PnLStatement
from app.storage import file_store

router = APIRouter(tags=["Financial Statements"])


def _path(deal_id: str, filename: str) -> Path:
    return file_store.get_processed_dir(deal_id) / filename


def _load(deal_id: str, filename: str, label: str) -> dict:
    p = _path(deal_id, filename)
    if not p.exists():
        raise HTTPException(
            status_code=404,
            detail=f"{label} not found for deal {deal_id}. Run /process (financial_builder stage) first.",
        )
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _rollup_annual(pnl: PnLStatement) -> PnLStatement:
    """
    Collapse a monthly PnLStatement into one row per (year, category, label).

    Summary dicts are keyed "YYYY" (e.g. "2022") instead of "YYYY-MM".
    Periods are set to Jan 1 of the corresponding year.
    Margins are recomputed from the aggregated annual totals.
    """
    # Aggregate amounts per (year, category, label) and preserve flags
    key_to_amount: dict[tuple, Decimal] = defaultdict(Decimal)
    key_to_flags: dict[tuple, dict] = {}

    for row in pnl.rows:
        key = (row.period.year, row.category, row.label)
        key_to_amount[key] += row.amount
        if key not in key_to_flags:
            key_to_flags[key] = {
                "is_revenue": row.is_revenue,
                "is_cogs": row.is_cogs,
                "is_opex": row.is_opex,
                "is_da": row.is_da,
                "is_below_ebitda": row.is_below_ebitda,
            }

    years = sorted({row.period.year for row in pnl.rows})
    annual_periods = [date(y, 1, 1) for y in years]

    annual_rows: list[PnLRow] = [
        PnLRow(
            period=date(year, 1, 1),
            category=cat,
            label=label,
            amount=amount,
            **key_to_flags[(year, cat, label)],
        )
        for (year, cat, label), amount in sorted(key_to_amount.items())
    ]

    # Rebuild summary dicts keyed by "YYYY"
    revenue: dict[str, Decimal] = {}
    gross_profit: dict[str, Decimal] = {}
    ebitda: dict[str, Decimal] = {}
    ebit: dict[str, Decimal] = {}
    net_income: dict[str, Decimal] = {}
    gross_margin: dict[str, float] = {}
    ebitda_margin: dict[str, float] = {}

    for yr in years:
        yk = str(yr)
        yr_rows = [r for r in annual_rows if r.period.year == yr]

        rev = sum((r.amount for r in yr_rows if r.is_revenue), Decimal("0"))
        cogs = sum((r.amount for r in yr_rows if r.is_cogs), Decimal("0"))
        opex = sum((r.amount for r in yr_rows if r.is_opex), Decimal("0"))
        da = sum((r.amount for r in yr_rows if r.is_da), Decimal("0"))
        below = sum((r.amount for r in yr_rows if r.is_below_ebitda), Decimal("0"))

        gp = rev + cogs
        ebitda_val = gp + opex
        ebit_val = ebitda_val + da
        ni = ebit_val + below

        revenue[yk] = rev
        gross_profit[yk] = gp
        ebitda[yk] = ebitda_val
        ebit[yk] = ebit_val
        net_income[yk] = ni
        gross_margin[yk] = float(gp / rev) if rev else 0.0
        ebitda_margin[yk] = float(ebitda_val / rev) if rev else 0.0

    return PnLStatement(
        deal_id=pnl.deal_id,
        periods=annual_periods,
        rows=annual_rows,
        revenue=revenue,
        gross_profit=gross_profit,
        ebitda=ebitda,
        ebit=ebit,
        net_income=net_income,
        gross_margin=gross_margin,
        ebitda_margin=ebitda_margin,
    )


@router.get("/deals/{deal_id}/financials/pnl", response_model=PnLStatement)
def get_pnl(
    deal_id: str,
    period: str | None = Query(
        default=None,
        description=(
            "Filter or rollup selector. "
            "'annual' → collapse to 3 annual periods. "
            "'2023' → filter to that year's months. "
            "'2023-06' → single month."
        ),
    ),
) -> PnLStatement:
    data = _load(deal_id, "financials_pnl.json", "P&L")
    pnl = PnLStatement.model_validate(data)

    if period == "annual":
        return _rollup_annual(pnl)

    if period:
        pnl.rows = [r for r in pnl.rows if r.period.strftime("%Y-%m").startswith(period)]
        pnl.periods = sorted({r.period for r in pnl.rows})
    return pnl


@router.get("/deals/{deal_id}/financials/balance-sheet", response_model=BalanceSheet)
def get_balance_sheet(deal_id: str) -> BalanceSheet:
    return BalanceSheet.model_validate(_load(deal_id, "financials_bs.json", "Balance Sheet"))


@router.get("/deals/{deal_id}/financials/cash-flow", response_model=CashFlowStatement)
def get_cash_flow(deal_id: str) -> CashFlowStatement:
    return CashFlowStatement.model_validate(_load(deal_id, "financials_cf.json", "Cash Flow"))


@router.get("/deals/{deal_id}/financials/summary")
def get_summary(deal_id: str) -> dict:
    """Key metrics summary — revenue, EBITDA, margins for every period."""
    data = _load(deal_id, "financials_pnl.json", "P&L")
    pnl = PnLStatement.model_validate(data)

    return {
        "deal_id": deal_id,
        "periods": [p.strftime("%Y-%m") for p in pnl.periods],
        "revenue": {k: str(v) for k, v in pnl.revenue.items()},
        "ebitda": {k: str(v) for k, v in pnl.ebitda.items()},
        "ebitda_margin_pct": {k: round(v * 100, 1) for k, v in pnl.ebitda_margin.items()},
        "gross_margin_pct": {k: round(v * 100, 1) for k, v in pnl.gross_margin.items()},
    }
