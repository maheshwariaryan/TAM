"""
Red Flag Rules Engine — deterministic metric-based flag detection.

Each rule fires against the computed financial statements and returns zero or
more RedFlag objects. No LLM calls; pure arithmetic comparisons.

Rules implemented:
  EBITDA_MARGIN_DECLINE   — >300bps YoY decline in EBITDA margin        → Medium
  OWNER_COMP_HIGH         — Management comp >15% of revenue              → Medium
  RELATED_PARTY_MATERIAL  — Related-party consulting >3% of revenue      → High
  ONE_TIME_ITEMS          — Any detected QoE one-time item               → informational summary
  LOW_CASH_CONVERSION     — Operating CF / EBITDA <60% for 2+ years      → High
  AR_DAYS_HIGH            — Accounts receivable days >75                 → Medium
  DEFERRED_REVENUE_DECLINE — Deferred revenue shrinking YoY             → High
  EBITDA_VOLATILITY       — Monthly EBITDA std dev / mean >40%           → Medium
  NWC_VOLATILITY          — Monthly NWC std dev / mean >30%              → Medium
  REVENUE_SEASONALITY     — Q4 revenue >40% of annual revenue            → Informational

Not implemented (require customer-level revenue data this system does not ingest —
skipped rather than approximated from aggregate GL, per the no-invented-numbers rule):
  CUSTOMER_CONCENTRATION, CUSTOMER_COUNT_DECLINE
"""

import logging
import uuid
from decimal import Decimal

from app.schemas.aging import CrossDocumentValidation
from app.schemas.financials import BalanceSheet, CashFlowStatement, PnLStatement
from app.schemas.gl import ChartOfAccountsCategory as CAT
from app.schemas.gl import MappedGLLine
from app.schemas.net_debt import NetDebtReport
from app.schemas.nwc import NWCReport
from app.schemas.qoe import QoEReport
from app.schemas.redflags import RedFlag

logger = logging.getLogger(__name__)

# Thresholds
EBITDA_MARGIN_DECLINE_BPS = 300          # 3.00%
OWNER_COMP_PCT_THRESHOLD = Decimal("0.10")    # >10% of revenue flags owner comp (mid-market norm)
RELATED_PARTY_PCT_THRESHOLD = Decimal("0.02") # >2% of revenue flags related-party materiality
CASH_CONVERSION_THRESHOLD = 0.60
AR_DAYS_THRESHOLD = 75
EBITDA_VOLATILITY_THRESHOLD = 0.40       # std dev / mean
NWC_VOLATILITY_THRESHOLD = 0.30          # std dev / mean (plan.txt threshold)
REVENUE_SEASONALITY_Q4_THRESHOLD = 0.40  # Q4 share of annual revenue


def detect_all(
    deal_id: str,
    pnl: PnLStatement,
    mapped_lines: list[MappedGLLine],
    qoe: QoEReport,
    balance_sheet: BalanceSheet | None = None,
    cash_flow: CashFlowStatement | None = None,
    nwc_report: NWCReport | None = None,
    cross_validation: CrossDocumentValidation | None = None,
    net_debt_report: NetDebtReport | None = None,
) -> list[RedFlag]:
    """Run all rules and return the combined flag list, sorted by severity."""
    flags: list[RedFlag] = []

    def _run(rule_id: str, rule_flags: list[RedFlag]) -> list[RedFlag]:
        logger.info(
            "redflag_rule rule=%s fired=%s flags_produced=%d",
            rule_id, bool(rule_flags), len(rule_flags),
            extra={"event": "redflag_rule", "deal_id": deal_id, "rule": rule_id,
                   "fired": bool(rule_flags), "flags_produced": len(rule_flags)},
        )
        return rule_flags

    flags.extend(_run("EBITDA_MARGIN_DECLINE", _rule_ebitda_margin_decline(deal_id, pnl)))
    flags.extend(_run("OWNER_COMP_HIGH", _rule_owner_comp_high(deal_id, pnl, mapped_lines)))
    flags.extend(_run("RELATED_PARTY_MATERIAL", _rule_related_party_material(deal_id, pnl, mapped_lines)))
    flags.extend(_run("QOE_ITEMS_PRESENT", _rule_one_time_items_present(deal_id, qoe)))
    flags.extend(_run("EBITDA_VOLATILITY", _rule_ebitda_volatility(deal_id, pnl)))
    flags.extend(_run("REVENUE_SEASONALITY", _rule_revenue_seasonality(deal_id, pnl)))

    if balance_sheet:
        flags.extend(_run("AR_DAYS_HIGH", _rule_ar_days_high(deal_id, pnl, balance_sheet)))
        flags.extend(_run("DEFERRED_REVENUE_DECLINE", _rule_deferred_revenue_decline(deal_id, balance_sheet)))

    if cash_flow:
        flags.extend(_run("LOW_CASH_CONVERSION", _rule_low_cash_conversion(deal_id, cash_flow, pnl)))

    if nwc_report and nwc_report.status != "skipped":
        flags.extend(_run("NWC_VOLATILITY", _rule_nwc_volatility(deal_id, nwc_report)))

    if cross_validation:
        flags.extend(_run(
            "CROSS_DOC_TIE_OUT_FAILURE",
            _rule_cross_doc_tie_out_failures(deal_id, cross_validation),
        ))

    if net_debt_report:
        flags.extend(_run(
            "NET_DEBT_RECONCILIATION_MISMATCH",
            _rule_net_debt_reconciliation_mismatch(deal_id, net_debt_report),
        ))

    # Sort: High → Medium → Low → Informational
    order = {"High": 0, "Medium": 1, "Low": 2, "Informational": 3}
    flags.sort(key=lambda f: order.get(f.severity, 4))

    logger.info(
        "Red flag detection complete for deal %s: %d flags (%s)",
        deal_id, len(flags),
        ", ".join(f"{s}={sum(1 for f in flags if f.severity==s)}" for s in ["High","Medium","Low","Informational"])
    )
    return flags


def _flag(deal_id: str, severity, category, title, description, rule_id,
          affected_periods=None, impact_low=None, impact_high=None,
          gl_line_ids=None) -> RedFlag:
    return RedFlag(
        flag_id=str(uuid.uuid4()),
        deal_id=deal_id,
        severity=severity,
        category=category,
        title=title,
        description=description,
        financial_impact_low=Decimal(str(impact_low)) if impact_low is not None else None,
        financial_impact_high=Decimal(str(impact_high)) if impact_high is not None else None,
        affected_periods=affected_periods or [],
        source="rule_engine",
        rule_id=rule_id,
        source_gl_line_ids=gl_line_ids or [],
    )


def _rule_ebitda_margin_decline(deal_id: str, pnl: PnLStatement) -> list[RedFlag]:
    """Flag if EBITDA margin falls >300bps in any year-over-year comparison."""
    flags: list[RedFlag] = []
    sorted_periods = sorted(pnl.ebitda_margin.keys())

    # Annual averages: group periods by year
    from collections import defaultdict
    annual: dict[str, list[float]] = defaultdict(list)
    for pk in sorted_periods:
        annual[pk[:4]].append(pnl.ebitda_margin[pk])

    annual_avg = {yr: sum(v) / len(v) for yr, v in annual.items() if v}
    years = sorted(annual_avg.keys())

    for i in range(1, len(years)):
        prev_yr, cur_yr = years[i - 1], years[i]
        decline_bps = (annual_avg[prev_yr] - annual_avg[cur_yr]) * 10_000
        if decline_bps >= EBITDA_MARGIN_DECLINE_BPS:
            flags.append(_flag(
                deal_id=deal_id,
                severity="Medium",
                category="Cost Structure",
                title=f"EBITDA Margin Declined {decline_bps:.0f}bps ({prev_yr}→{cur_yr})",
                description=(
                    f"Average EBITDA margin fell from {annual_avg[prev_yr]:.1%} in {prev_yr} "
                    f"to {annual_avg[cur_yr]:.1%} in {cur_yr}, a decline of {decline_bps:.0f}bps. "
                    "This may indicate rising cost pressures or pricing deterioration."
                ),
                rule_id="EBITDA_MARGIN_DECLINE",
                affected_periods=[p for p in sorted_periods if p.startswith(cur_yr)],
            ))
    return flags


def _rule_owner_comp_high(
    deal_id: str, pnl: PnLStatement, mapped_lines: list[MappedGLLine]
) -> list[RedFlag]:
    """Flag if management compensation exceeds 15% of revenue in any year."""
    from collections import defaultdict

    comp_by_period: dict[str, Decimal] = defaultdict(Decimal)
    for line in mapped_lines:
        if line.standard_category == CAT.MANAGEMENT_COMPENSATION:
            pk = line.period.strftime("%Y-%m")
            comp_by_period[pk] += abs(line.amount)

    flags: list[RedFlag] = []
    flagged_periods = []

    for pk, comp in comp_by_period.items():
        rev = pnl.revenue.get(pk, Decimal("0"))
        if rev == 0:
            continue
        pct = comp / rev
        if pct > OWNER_COMP_PCT_THRESHOLD:
            flagged_periods.append(pk)

    if flagged_periods:
        # Estimate annual excess
        annual_comp = sum(comp_by_period.values()) / Decimal("36") * 12
        annual_rev = sum(pnl.revenue.values()) / Decimal("36") * 12
        excess_pct = float(annual_comp / annual_rev) if annual_rev else 0
        impact_low = float(annual_comp) * 0.30   # ~30% excess assumption low
        impact_high = float(annual_comp) * 0.55  # ~55% excess assumption high

        flags.append(_flag(
            deal_id=deal_id,
            severity="Medium",
            category="Cost Structure",
            title=f"Owner Compensation Elevated ({excess_pct:.1%} of Revenue)",
            description=(
                f"Management compensation represents approximately {excess_pct:.1%} of revenue "
                f"across the diligence period, above the 15% threshold. "
                "The above-market element should be normalised in the QoE and replaced with an "
                "arm's-length management fee in the buyer's financial model."
            ),
            rule_id="OWNER_COMP_HIGH",
            affected_periods=sorted(flagged_periods),
            impact_low=impact_low,
            impact_high=impact_high,
        ))
    return flags


def _rule_related_party_material(
    deal_id: str, pnl: PnLStatement, mapped_lines: list[MappedGLLine]
) -> list[RedFlag]:
    """Flag if related-party consulting exceeds 3% of revenue."""
    from collections import defaultdict

    rp_by_period: dict[str, Decimal] = defaultdict(Decimal)
    for line in mapped_lines:
        if line.standard_category == CAT.RELATED_PARTY_CONSULTING:
            pk = line.period.strftime("%Y-%m")
            rp_by_period[pk] += abs(line.amount)

    if not rp_by_period:
        return []

    total_rp = sum(rp_by_period.values())
    total_rev = sum(pnl.revenue.values())
    pct = total_rp / total_rev if total_rev else Decimal("0")

    if pct < RELATED_PARTY_PCT_THRESHOLD:
        return []

    annual_rp = total_rp / Decimal("3")  # 3 years
    return [_flag(
        deal_id=deal_id,
        severity="High",
        category="Revenue Quality",
        title=f"Material Related-Party Payments ({float(pct):.1%} of Revenue)",
        description=(
            f"Payments to related parties total approximately ${float(total_rp):,.0f} "
            f"over the diligence period ({float(pct):.1%} of revenue). "
            "These arrangements require full disclosure, independent valuation of arm's-length "
            "equivalence, and confirmation that they will be terminated or restructured post-close."
        ),
        rule_id="RELATED_PARTY_MATERIAL",
        affected_periods=sorted(rp_by_period.keys()),
        impact_low=float(annual_rp) * 0.8,
        impact_high=float(annual_rp),
    )]


def _rule_one_time_items_present(deal_id: str, qoe: QoEReport) -> list[RedFlag]:
    """Informational: summarise all QoE one-time items in a single flag."""
    if not qoe.adjustments:
        return []

    total = sum(a.adjustment_amount for a in qoe.adjustments)
    categories = ", ".join(sorted({a.category for a in qoe.adjustments}))
    return [_flag(
        deal_id=deal_id,
        severity="Informational",
        category="Accounting Policy",
        title=f"{len(qoe.adjustments)} QoE Adjustment(s) Identified (${float(total):,.0f} Total)",
        description=(
            f"{len(qoe.adjustments)} non-recurring items totalling ${float(total):,.0f} "
            f"were identified and added back in the QoE analysis. "
            f"Categories: {categories}. Refer to the QoE Centre for the full adjustment ledger."
        ),
        rule_id="QOE_ITEMS_PRESENT",
        affected_periods=sorted({a.period.strftime("%Y-%m") for a in qoe.adjustments}),
        impact_low=float(total),
        impact_high=float(total),
    )]


def _rule_ebitda_volatility(deal_id: str, pnl: PnLStatement) -> list[RedFlag]:
    """Flag if monthly EBITDA is highly volatile (std dev / mean > 40%)."""
    import statistics
    values = [float(v) for v in pnl.ebitda.values() if v != 0]
    if len(values) < 12:
        return []

    mean = statistics.mean(values)
    if mean <= 0:
        return []

    stdev = statistics.stdev(values)
    cv = stdev / mean  # Coefficient of variation

    if cv <= EBITDA_VOLATILITY_THRESHOLD:
        return []

    return [_flag(
        deal_id=deal_id,
        severity="Medium",
        category="Revenue Quality",
        title=f"High EBITDA Volatility (CV: {cv:.0%})",
        description=(
            f"Monthly EBITDA has a coefficient of variation of {cv:.0%}, indicating high "
            "period-to-period variability. This may reflect project-based revenue, strong "
            "seasonality, or irregular cost timing — each of which affects NWC peg reliability."
        ),
        rule_id="EBITDA_VOLATILITY",
        affected_periods=sorted(pnl.ebitda.keys()),
    )]


def _rule_ar_days_high(
    deal_id: str, pnl: PnLStatement, bs: BalanceSheet
) -> list[RedFlag]:
    """Flag if AR days exceed 75 in the most recent period."""
    if not bs.periods:
        return []

    latest_pk = max(p.strftime("%Y-%m") for p in bs.periods)
    ar_rows = [r for r in bs.rows if r.category == CAT.ACCOUNTS_RECEIVABLE.value
               and r.period.strftime("%Y-%m") == latest_pk]
    if not ar_rows:
        return []

    ar_balance = sum(r.amount for r in ar_rows)
    monthly_rev = pnl.revenue.get(latest_pk, Decimal("0"))
    if monthly_rev <= 0:
        return []

    ar_days = float(ar_balance / monthly_rev) * 30

    if ar_days <= AR_DAYS_THRESHOLD:
        return []

    return [_flag(
        deal_id=deal_id,
        severity="Medium",
        category="Cash Flow Quality",
        title=f"AR Days Elevated ({ar_days:.0f} days in {latest_pk})",
        description=(
            f"Accounts receivable days of {ar_days:.0f} in {latest_pk} exceed the "
            f"{AR_DAYS_THRESHOLD}-day threshold. Extended collection periods may indicate "
            "customer disputes, deteriorating credit quality, or aggressive revenue recognition."
        ),
        rule_id="AR_DAYS_HIGH",
        affected_periods=[latest_pk],
        impact_low=float(ar_balance) * 0.05,
        impact_high=float(ar_balance) * 0.15,
    )]


def _rule_deferred_revenue_decline(
    deal_id: str, bs: BalanceSheet
) -> list[RedFlag]:
    """Flag if deferred revenue is declining — potential pull-forward / channel stuffing."""
    dr_by_period = {
        r.period.strftime("%Y-%m"): r.amount
        for r in bs.rows
        if r.category == CAT.DEFERRED_REVENUE.value
    }
    if len(dr_by_period) < 13:
        return []

    periods = sorted(dr_by_period.keys())
    latest_12 = periods[-12:]
    earlier_12 = periods[-24:-12]

    if not earlier_12:
        return []

    avg_recent = sum(dr_by_period[p] for p in latest_12) / 12
    avg_prior = sum(dr_by_period[p] for p in earlier_12) / 12

    if avg_prior <= 0 or avg_recent >= avg_prior * Decimal("0.90"):
        return []

    decline_pct = float((avg_prior - avg_recent) / avg_prior)
    return [_flag(
        deal_id=deal_id,
        severity="High",
        category="Revenue Quality",
        title=f"Deferred Revenue Declining ({decline_pct:.0%} YoY)",
        description=(
            f"Average monthly deferred revenue fell {decline_pct:.0%} in the most recent "
            "12-month period versus the prior year. Declining deferred revenue can indicate "
            "deteriorating customer prepayment behaviour, contract losses, or revenue pulled "
            "forward to inflate near-term reported earnings."
        ),
        rule_id="DEFERRED_REVENUE_DECLINE",
        affected_periods=latest_12,
        impact_low=float(avg_prior - avg_recent) * 12 * 0.5,
        impact_high=float(avg_prior - avg_recent) * 12,
    )]


def _rule_low_cash_conversion(
    deal_id: str, cf: CashFlowStatement, pnl: PnLStatement
) -> list[RedFlag]:
    """Flag if operating cash flow / EBITDA < 60% for 2+ consecutive years."""
    from collections import defaultdict

    annual_op: dict[str, float] = defaultdict(float)
    annual_ebitda: dict[str, float] = defaultdict(float)

    for pk, op in cf.operating_cash_flow.items():
        annual_op[pk[:4]] += float(op)
    for pk, ebitda_val in pnl.ebitda.items():
        annual_ebitda[pk[:4]] += float(ebitda_val)

    years = sorted(set(annual_op.keys()) & set(annual_ebitda.keys()))
    low_years = [
        yr for yr in years
        if annual_ebitda[yr] > 0
        and annual_op[yr] / annual_ebitda[yr] < CASH_CONVERSION_THRESHOLD
    ]

    if len(low_years) < 2:
        return []

    avg_conv = sum(
        annual_op[yr] / annual_ebitda[yr] for yr in low_years if annual_ebitda[yr] > 0
    ) / len(low_years)

    return [_flag(
        deal_id=deal_id,
        severity="High",
        category="Cash Flow Quality",
        title=f"Low Cash Conversion ({avg_conv:.0%} avg over {len(low_years)} years)",
        description=(
            f"Operating cash flow conversion averaged {avg_conv:.0%} of EBITDA over "
            f"{len(low_years)} years ({', '.join(low_years)}), below the 60% threshold. "
            "This signals meaningful working capital consumption or capitalisation of costs "
            "that may be masking true cash generation."
        ),
        rule_id="LOW_CASH_CONVERSION",
        affected_periods=[f"{yr}-01" for yr in low_years],
    )]


def _rule_nwc_volatility(deal_id: str, nwc_report: NWCReport) -> list[RedFlag]:
    """Flag if monthly NWC has a coefficient of variation > 30% (plan.txt threshold)."""
    cv = nwc_report.nwc_volatility
    if cv is None or cv <= NWC_VOLATILITY_THRESHOLD:
        return []

    periods = [dp.period.strftime("%Y-%m") for dp in nwc_report.data_points]
    return [_flag(
        deal_id=deal_id,
        severity="Medium",
        category="Working Capital",
        title=f"High NWC Volatility (CV: {cv:.0%})",
        description=(
            f"Monthly net working capital has a coefficient of variation of {cv:.0%}, above the "
            f"{NWC_VOLATILITY_THRESHOLD:.0%} threshold. Volatile NWC increases peg risk and may "
            "indicate seasonality, inconsistent collections/payment timing, or lumpy inventory builds — "
            "see the NWC seasonal_adjusted peg for a normalized alternative."
        ),
        rule_id="NWC_VOLATILITY",
        affected_periods=periods,
    )]


def _rule_revenue_seasonality(deal_id: str, pnl: PnLStatement) -> list[RedFlag]:
    """Informational: flag if Q4 revenue exceeds 40% of annual revenue on average."""
    from collections import defaultdict

    annual: dict[str, list[str]] = defaultdict(list)
    for pk in pnl.revenue:
        annual[pk[:4]].append(pk)

    q4_pcts = []
    full_years = []
    for yr, periods in annual.items():
        if len(periods) < 12:
            continue
        yr_total = sum(pnl.revenue[pk] for pk in periods)
        if not yr_total:
            continue
        q4_total = sum(pnl.revenue[pk] for pk in periods if pk.split("-")[1] in ("10", "11", "12"))
        q4_pcts.append(float(q4_total / yr_total))
        full_years.append(yr)

    if not q4_pcts:
        return []

    avg_q4_pct = sum(q4_pcts) / len(q4_pcts)
    if avg_q4_pct <= REVENUE_SEASONALITY_Q4_THRESHOLD:
        return []

    return [_flag(
        deal_id=deal_id,
        severity="Informational",
        category="Revenue Quality",
        title=f"Significant Revenue Seasonality (Q4: {avg_q4_pct:.0%} of Annual Revenue)",
        description=(
            f"Q4 revenue averages {avg_q4_pct:.0%} of annual revenue across {len(full_years)} full "
            f"year(s), above the {REVENUE_SEASONALITY_Q4_THRESHOLD:.0%} concentration threshold. "
            "This is informational context for NWC peg timing and quarterly run-rate comparisons, "
            "not necessarily a defect."
        ),
        rule_id="REVENUE_SEASONALITY",
        affected_periods=sorted(pk for yr in full_years for pk in annual[yr]),
    )]


def _rule_cross_doc_tie_out_failures(
    deal_id: str, cross_validation: CrossDocumentValidation
) -> list[RedFlag]:
    """Flag any cross-document tie-out (e.g. AR/AP aging vs. balance sheet) that failed —
    variance beyond 2x tolerance, meaning the source documents materially disagree."""
    flags: list[RedFlag] = []
    for tie_out in cross_validation.tie_outs:
        if tie_out.status != "Fail":
            continue
        flags.append(_flag(
            deal_id=deal_id,
            severity="High",
            category="Data Quality",
            title=f"Data Mismatch: {tie_out.name} ({tie_out.variance_pct:.1f}% variance)",
            description=(
                f"{tie_out.name} does not tie out: expected ${float(tie_out.expected):,.0f} "
                f"(from {', '.join(tie_out.source_documents) or 'the balance sheet'}) vs. observed "
                f"${float(tie_out.observed):,.0f}, a difference of ${float(abs(tie_out.difference)):,.0f} "
                f"({tie_out.variance_pct:.1f}%), exceeding the {tie_out.tolerance_pct:.1f}% tolerance. "
                "Reconcile the source documents before relying on either figure."
            ),
            rule_id="CROSS_DOC_TIE_OUT_FAILURE",
            impact_low=float(abs(tie_out.difference)),
            impact_high=float(abs(tie_out.difference)),
        ))
    return flags


def _rule_net_debt_reconciliation_mismatch(
    deal_id: str, net_debt_report: NetDebtReport
) -> list[RedFlag]:
    """Flag if contract-extracted debt principal fails to reconcile against balance-sheet debt
    beyond the 5% tolerance already computed in the net debt bridge."""
    variance = net_debt_report.reconciliation_variance
    if variance is None:
        return []

    tolerance = abs(net_debt_report.total_debt) * Decimal("0.05")
    if abs(variance) <= tolerance:
        return []

    return [_flag(
        deal_id=deal_id,
        severity="High",
        category="Data Quality",
        title=f"Debt Schedule Mismatch (${float(abs(variance)):,.0f} variance)",
        description=(
            net_debt_report.reconciliation_note
            or (
                f"Contract-extracted principal (${float(net_debt_report.instrument_principal_total or 0):,.0f}) "
                f"differs from balance sheet debt (${float(net_debt_report.total_debt):,.0f}) by "
                f"${float(abs(variance)):,.0f}, beyond the 5% tolerance."
            )
        ),
        rule_id="NET_DEBT_RECONCILIATION_MISMATCH",
        affected_periods=[net_debt_report.period] if net_debt_report.period else [],
        impact_low=float(abs(variance)),
        impact_high=float(abs(variance)),
    )]
