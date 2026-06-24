"""Cross-document tie-out validation (AR/AP aging vs GL balance sheet)."""

import logging
from decimal import Decimal

from app.schemas.aging import AgingReport, CrossDocumentValidation, TieOutResult
from app.schemas.gl import ChartOfAccountsCategory, MappedGLLine, RawGLLine

logger = logging.getLogger(__name__)

AR_TOLERANCE_PCT = 0.5
AP_TOLERANCE_PCT = 1.0


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

    logger.info("Cross-document validation for %s: %d tie-outs", deal_id, len(tie_outs))
    return CrossDocumentValidation(deal_id=deal_id, tie_outs=tie_outs, warnings=warnings)
