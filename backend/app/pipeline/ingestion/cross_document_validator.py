"""Cross-document tie-out validation (AR/AP aging vs GL balance sheet, and Group A
supporting-schedule reconciliation vs GL-derived financial statements)."""

import logging
from decimal import Decimal, InvalidOperation

from app.schemas.aging import AgingReport, CrossDocumentValidation, TieOutResult
from app.schemas.financials import BalanceSheet, CashFlowStatement, PnLStatement
from app.schemas.gl import ChartOfAccountsCategory, MappedGLLine, RawGLLine

logger = logging.getLogger(__name__)

AR_TOLERANCE_PCT = 0.5
AP_TOLERANCE_PCT = 1.0
SCHEDULE_TIE_OUT_TOLERANCE_PCT = 1.0


def _latest_aging_total(summaries: list, period_key: str | None = None) -> tuple[Decimal, str]:
    if not summaries:
        return Decimal("0"), ""
    if period_key:
        matching = [s for s in summaries if s.period.strftime("%Y-%m") == period_key]
        if matching:
            s = matching[-1]
            return s.total, s.source_file
    s = max(summaries, key=lambda x: x.period)
    return s.total, s.source_file


def _gl_bs_balance(
    lines: list[RawGLLine] | list[MappedGLLine],
    account_prefix: str,
    category: ChartOfAccountsCategory | None = None,
    period_key: str | None = None,
) -> Decimal:
    total = Decimal("0")
    for line in lines:
        if period_key and line.period.strftime("%Y-%m") != period_key:
            continue
        if category and hasattr(line, "standard_category"):
            if line.standard_category != category:
                continue
            total += abs(line.amount)
            continue
        if line.account_code.startswith(account_prefix):
            total += abs(line.amount)
    return total


def _tie_out(name: str, expected: Decimal, observed: Decimal, tolerance_pct: float, sources: list[str]) -> TieOutResult:
    diff = observed - expected
    variance_pct = float(abs(diff) / expected * 100) if expected else (100.0 if observed else 0.0)
    if variance_pct <= tolerance_pct:
        status = "Pass"
    elif variance_pct <= tolerance_pct * 2:
        status = "Warn"
    else:
        status = "Fail"

    log_fn = logger.info if status == "Pass" else logger.warning
    log_fn(
        "tie_out check=%s status=%s expected=%s observed=%s difference=%s "
        "variance_pct=%.2f%% tolerance_pct=%.2f%% sources=%s",
        name, status, expected, observed, diff, variance_pct, tolerance_pct, sources,
        extra={
            "event": "tie_out", "check": name, "status": status,
            "expected": str(expected), "observed": str(observed), "difference": str(diff),
            "variance_pct": round(variance_pct, 2), "tolerance_pct": tolerance_pct,
            "source_documents": sources,
        },
    )

    return TieOutResult(
        name=name,
        expected=expected,
        observed=observed,
        difference=diff,
        variance_pct=round(variance_pct, 2),
        tolerance_pct=tolerance_pct,
        status=status,  # type: ignore[arg-type]
        source_documents=sources,
    )


def validate_cross_documents(
    deal_id: str,
    gl_lines: list[RawGLLine],
    ar_report: AgingReport | None,
    ap_report: AgingReport | None,
    mapped_lines: list[MappedGLLine] | None = None,
) -> CrossDocumentValidation:
    """Run AR/AP aging tie-outs against GL balance sheet balances."""
    tie_outs: list[TieOutResult] = []
    warnings: list[str] = []
    bs_lines = mapped_lines or gl_lines

    if ar_report and ar_report.summaries:
        ar_total, ar_src = _latest_aging_total(ar_report.summaries)
        period_key = max(ar_report.summaries, key=lambda x: x.period).period.strftime("%Y-%m")
        gl_ar = _gl_bs_balance(
            bs_lines,
            "1002",
            ChartOfAccountsCategory.ACCOUNTS_RECEIVABLE if mapped_lines else None,
            period_key,
        )
        if gl_ar == 0:
            gl_ar = _gl_bs_balance(bs_lines, "1002", None, period_key)
        tie_outs.append(
            _tie_out("AR Aging <-> BS AR", gl_ar, ar_total, AR_TOLERANCE_PCT, [ar_src])
        )
    elif ar_report is None:
        warnings.append("AR aging not uploaded — AR <-> BS tie-out skipped")

    if ap_report and ap_report.summaries:
        ap_total, ap_src = _latest_aging_total(ap_report.summaries)
        period_key = max(ap_report.summaries, key=lambda x: x.period).period.strftime("%Y-%m")
        gl_ap = _gl_bs_balance(
            bs_lines,
            "2001",
            ChartOfAccountsCategory.ACCOUNTS_PAYABLE if mapped_lines else None,
            period_key,
        )
        if gl_ap == 0:
            gl_ap = _gl_bs_balance(bs_lines, "2001", None, period_key)
        tie_outs.append(
            _tie_out("AP Aging <-> BS AP", gl_ap, ap_total, AP_TOLERANCE_PCT, [ap_src])
        )
    elif ap_report is None:
        warnings.append("AP aging not uploaded — AP <-> BS tie-out skipped")

    status_counts: dict[str, int] = {}
    for t in tie_outs:
        status_counts[t.status] = status_counts.get(t.status, 0) + 1
    log_fn = logger.warning if status_counts.get("Fail") else logger.info
    log_fn(
        "cross_document_validation_complete deal_id=%s tie_outs=%d %s",
        deal_id, len(tie_outs), status_counts,
        extra={
            "event": "cross_document_validation_complete", "deal_id": deal_id,
            "tie_out_count": len(tie_outs), "status_counts": status_counts,
        },
    )
    return CrossDocumentValidation(deal_id=deal_id, tie_outs=tie_outs, warnings=warnings)


def _schedule_value(schedule: dict, label: str, period_key: str) -> Decimal | None:
    periods = schedule.get(label)
    if not periods or period_key not in periods:
        return None
    try:
        return Decimal(str(periods[period_key]))
    except InvalidOperation:
        return None


def _schedule_period_total(schedule: dict, period_key: str) -> Decimal | None:
    """Sum every label's value at a given period — used for account-level schedules
    (revenue/cogs/opex) where each row is one account, not a named total. Excludes any
    row whose label itself is a subtotal/total row (these files commonly end with a
    trailing "TOTAL" row) — including it would double-count against the per-account sum."""
    values = [
        Decimal(str(v[period_key]))
        for label, v in schedule.items()
        if period_key in v and "total" not in label.lower()
    ]
    return sum(values, Decimal("0")) if values else None


def _schedule_periods(schedule: dict) -> set[str]:
    periods: set[str] = set()
    for label_periods in schedule.values():
        periods.update(label_periods.keys())
    return periods


def _bs_row_amount(bs: BalanceSheet, category: ChartOfAccountsCategory, period_key: str) -> Decimal:
    return sum(
        (
            row.amount for row in bs.rows
            if row.category == category.value and row.period.strftime("%Y-%m") == period_key
        ),
        Decimal("0"),
    )


def _pnl_rows_total(pnl: PnLStatement, period_key: str, *, is_cogs: bool = False, is_opex: bool = False) -> Decimal:
    return sum(
        (
            row.amount for row in pnl.rows
            if row.period.strftime("%Y-%m") == period_key
            and (row.is_cogs if is_cogs else row.is_opex)
        ),
        Decimal("0"),
    )


def reconcile_schedules(
    schedule_data: dict[str, dict],
    pnl: PnLStatement | None,
    bs: BalanceSheet | None,
    cash_flow: CashFlowStatement | None,
) -> list[TieOutResult]:
    """Reconcile Group A supporting schedules (balance sheet, income statement, cash
    flow, revenue, COGS, opex, working capital, inventory rollforward) against the
    GL-derived statements already built by financial_builder. These schedules are never
    used to recompute the GL-derived figures — only to flag when they disagree, the same
    principle net_debt_bridge already applies to contract-extracted debt detail."""
    tie_outs: list[TieOutResult] = []

    if bs is not None and bs.periods:
        bs_periods = {p.strftime("%Y-%m") for p in bs.periods}

        bs_schedule = schedule_data.get("balance_sheet")
        if bs_schedule:
            pk = max(_schedule_periods(bs_schedule) & bs_periods, default=None)
            if pk:
                for label, field in (
                    ("Total Assets", "total_assets"),
                    ("Total Liabilities", "total_liabilities"),
                    ("Total Equity", "total_equity"),
                ):
                    observed = _schedule_value(bs_schedule, label, pk)
                    expected = getattr(bs, field).get(pk)
                    if observed is not None and expected is not None:
                        tie_outs.append(_tie_out(
                            f"Balance Sheet Schedule <-> {label}", expected, observed,
                            SCHEDULE_TIE_OUT_TOLERANCE_PCT, ["balance_sheet_schedule"],
                        ))

        wc_schedule = schedule_data.get("working_capital")
        if wc_schedule:
            pk = max(_schedule_periods(wc_schedule) & bs_periods, default=None)
            if pk:
                for label, category in (
                    ("AR", ChartOfAccountsCategory.ACCOUNTS_RECEIVABLE),
                    ("Inventory", ChartOfAccountsCategory.INVENTORY),
                    ("AP", ChartOfAccountsCategory.ACCOUNTS_PAYABLE),
                ):
                    observed = _schedule_value(wc_schedule, label, pk)
                    if observed is not None:
                        expected = _bs_row_amount(bs, category, pk)
                        tie_outs.append(_tie_out(
                            f"Working Capital Schedule <-> BS {label}", expected, observed,
                            SCHEDULE_TIE_OUT_TOLERANCE_PCT, ["working_capital_schedule"],
                        ))

        inv_schedule = schedule_data.get("inventory")
        if inv_schedule:
            pk = max(_schedule_periods(inv_schedule) & bs_periods, default=None)
            observed = _schedule_value(inv_schedule, "Ending Inventory", pk) if pk else None
            if observed is not None:
                expected = _bs_row_amount(bs, ChartOfAccountsCategory.INVENTORY, pk)
                tie_outs.append(_tie_out(
                    "Inventory Rollforward <-> BS Inventory", expected, observed,
                    SCHEDULE_TIE_OUT_TOLERANCE_PCT, ["inventory_rollforward"],
                ))

    if pnl is not None and pnl.periods:
        pnl_periods = {p.strftime("%Y-%m") for p in pnl.periods}

        is_schedule = schedule_data.get("income_statement")
        if is_schedule:
            pk = max(_schedule_periods(is_schedule) & pnl_periods, default=None)
            if pk:
                for label, field in (
                    ("Total Revenue", "revenue"),
                    ("Gross Profit", "gross_profit"),
                    ("EBITDA", "ebitda"),
                    ("Net Income", "net_income"),
                ):
                    observed = _schedule_value(is_schedule, label, pk)
                    expected = getattr(pnl, field).get(pk)
                    if observed is not None and expected is not None:
                        tie_outs.append(_tie_out(
                            f"Income Statement Schedule <-> {label}", expected, observed,
                            SCHEDULE_TIE_OUT_TOLERANCE_PCT, ["income_statement_schedule"],
                        ))

        revenue_schedule = schedule_data.get("revenue")
        if revenue_schedule:
            pk = max(_schedule_periods(revenue_schedule) & pnl_periods, default=None)
            observed = _schedule_period_total(revenue_schedule, pk) if pk else None
            expected = pnl.revenue.get(pk) if pk else None
            if observed is not None and expected is not None:
                tie_outs.append(_tie_out(
                    "Revenue Schedule <-> P&L Revenue", expected, observed,
                    SCHEDULE_TIE_OUT_TOLERANCE_PCT, ["revenue_schedule"],
                ))

        cogs_schedule = schedule_data.get("cogs")
        if cogs_schedule:
            pk = max(_schedule_periods(cogs_schedule) & pnl_periods, default=None)
            observed = _schedule_period_total(cogs_schedule, pk) if pk else None
            if observed is not None:
                expected = abs(_pnl_rows_total(pnl, pk, is_cogs=True))
                tie_outs.append(_tie_out(
                    "COGS Schedule <-> P&L COGS", expected, observed,
                    SCHEDULE_TIE_OUT_TOLERANCE_PCT, ["cogs_schedule"],
                ))

        opex_schedule = schedule_data.get("opex")
        if opex_schedule:
            pk = max(_schedule_periods(opex_schedule) & pnl_periods, default=None)
            observed = _schedule_period_total(opex_schedule, pk) if pk else None
            if observed is not None:
                expected = abs(_pnl_rows_total(pnl, pk, is_opex=True))
                tie_outs.append(_tie_out(
                    "Opex Schedule <-> P&L Opex", expected, observed,
                    SCHEDULE_TIE_OUT_TOLERANCE_PCT, ["opex_schedule"],
                ))

    if cash_flow is not None and cash_flow.periods:
        cf_periods = {p.strftime("%Y-%m") for p in cash_flow.periods}
        cf_schedule = schedule_data.get("cash_flow")
        if cf_schedule:
            pk = max(_schedule_periods(cf_schedule) & cf_periods, default=None)
            if pk:
                for label, field in (
                    ("Cash from Operations", "operating_cash_flow"),
                    ("Cash from Investing", "investing_cash_flow"),
                    ("Cash from Financing", "financing_cash_flow"),
                    ("Net Change in Cash", "net_cash_flow"),
                ):
                    observed = _schedule_value(cf_schedule, label, pk)
                    expected = getattr(cash_flow, field).get(pk)
                    if observed is not None and expected is not None:
                        tie_outs.append(_tie_out(
                            f"Cash Flow Schedule <-> {label}", expected, observed,
                            SCHEDULE_TIE_OUT_TOLERANCE_PCT, ["cash_flow_schedule"],
                        ))

    return tie_outs
