"""
NWC Analyzer — deterministic net working capital analysis + commercial health.

Computes, purely from Python/Decimal/statistics (no LLM arithmetic):
  - Monthly NWC data points from the already-built Balance Sheet
    (NWC_COMPONENTS categories in schemas/gl.py), so every figure traces
    back through the balance sheet builder to source GL lines.
  - Three NWC peg candidates (ltm_average, median_trailing_12,
    seasonal_adjusted when >=24 months of history are available), with a
    recommended method + rationale.
  - Working-capital ratios: DSO, DPO, DIO, cash conversion cycle, and
    AR/AP >60-day aging percentages (when aging summaries were ingested).
  - A commercial-health report of deterministic growth/margin/volatility
    metrics. Customer-level metrics (concentration, churn, customer count)
    are intentionally NOT faked here — this system does not ingest
    customer-level revenue data. See CommercialHealthReport docstring.
"""

import json
import logging
import statistics
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from app.schemas.aging import AgingReport, AgingSummary
from app.schemas.financials import BalanceSheet, PnLStatement
from app.schemas.gl import NWC_COMPONENTS
from app.schemas.gl import ChartOfAccountsCategory as CAT
from app.schemas.nwc import (
    CommercialHealthReport,
    NWCDataPoint,
    NWCPeg,
    NWCReport,
    WorkingCapitalRatios,
)
from app.storage import file_store

logger = logging.getLogger(__name__)

# NWC_COMPONENTS categories split by presentation sign (matches balance_sheet.py sections)
_ASSET_CATEGORIES = {
    CAT.ACCOUNTS_RECEIVABLE, CAT.INVENTORY, CAT.PREPAID_EXPENSES, CAT.OTHER_CURRENT_ASSETS,
}
_LIABILITY_CATEGORIES = {
    CAT.ACCOUNTS_PAYABLE, CAT.ACCRUED_LIABILITIES, CAT.DEFERRED_REVENUE,
    CAT.CURRENT_DEBT, CAT.OTHER_CURRENT_LIABILITIES,
}

_SEASONALITY_THRESHOLD = 0.15   # (max monthly avg - min monthly avg) / overall avg
_OUTLIER_SKEW_THRESHOLD = 0.15  # |mean - median| / mean
_MIN_MONTHS_FOR_SEASONALITY = 24
_AR_AP_OVER_60_BUCKETS = ("bucket_61_90", "bucket_90_plus")


class NWCAnalyzerError(Exception):
    pass


def _path(deal_id: str, filename: str) -> Path:
    return file_store.get_processed_dir(deal_id) / filename


def _try_load(deal_id: str, filename: str, model_class):
    p = _path(deal_id, filename)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return model_class.model_validate(json.load(f))


def run(deal_id: str) -> dict:
    bs = _try_load(deal_id, "financials_bs.json", BalanceSheet)
    pnl = _try_load(deal_id, "financials_pnl.json", PnLStatement)
    ar_aging = _try_load(deal_id, "ar_aging.json", AgingReport)
    ap_aging = _try_load(deal_id, "ap_aging.json", AgingReport)

    nwc_report = _build_nwc_report(deal_id, bs, pnl, ar_aging, ap_aging)
    commercial_report = _build_commercial_report(deal_id, pnl)

    _save(nwc_report.model_dump(mode="json"), _path(deal_id, "nwc_report.json"))
    _save(commercial_report.model_dump(mode="json"), _path(deal_id, "commercial_report.json"))

    logger.info(
        "NWC analyzer complete for %s: status=%s, %d data points, %d pegs",
        deal_id, nwc_report.status, len(nwc_report.data_points), len(nwc_report.pegs),
    )
    return {"nwc": nwc_report.model_dump(mode="json"), "commercial": commercial_report.model_dump(mode="json")}


def _save(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


# ── NWC report ───────────────────────────────────────────────────────────────

def _build_nwc_report(
    deal_id: str,
    bs: BalanceSheet | None,
    pnl: PnLStatement | None,
    ar_aging: AgingReport | None,
    ap_aging: AgingReport | None,
) -> NWCReport:
    if bs is None:
        return NWCReport(
            deal_id=deal_id,
            status="skipped",
            message=(
                "Balance sheet unavailable — NWC analysis requires mapped GL with balance "
                "sheet accounts (AR, Inventory, Prepaids, AP, Accruals). Run financial_builder first."
            ),
            has_ar_aging=ar_aging is not None,
            has_ap_aging=ap_aging is not None,
        )

    data_points = _build_data_points(bs, pnl)
    if not data_points:
        return NWCReport(
            deal_id=deal_id,
            status="skipped",
            message="No NWC-component balance sheet categories found for this deal.",
            has_ar_aging=ar_aging is not None,
            has_ap_aging=ap_aging is not None,
        )

    monthly_nwc: dict[str, Decimal] = {
        dp.period.strftime("%Y-%m"): dp.net_working_capital for dp in data_points
    }
    pegs = _compute_pegs(monthly_nwc)

    values = [float(v) for v in monthly_nwc.values()]
    mean_val = statistics.mean(values)
    volatility = (statistics.pstdev(values) / mean_val) if mean_val and len(values) >= 2 else None

    sorted_periods = sorted(monthly_nwc.keys())
    peak_pk = max(sorted_periods, key=lambda pk: monthly_nwc[pk])
    trough_pk = min(sorted_periods, key=lambda pk: monthly_nwc[pk])

    ratios = _compute_ratios(data_points, pnl, ar_aging, ap_aging)

    has_ar = ar_aging is not None
    has_ap = ap_aging is not None
    status = "complete" if (has_ar and has_ap) else "partial"
    message = (
        "NWC peg and trend computed from balance sheet history."
        if status == "complete"
        else (
            "NWC peg and trend computed from balance sheet history. AR/AP aging not uploaded — "
            "60+ day aging percentages unavailable; upload aging summaries to complete the analysis."
        )
    )

    return NWCReport(
        deal_id=deal_id,
        status=status,
        message=message,
        has_ar_aging=has_ar,
        has_ap_aging=has_ap,
        data_points=data_points,
        pegs=pegs,
        peak_nwc=monthly_nwc[peak_pk],
        peak_period=peak_pk,
        trough_nwc=monthly_nwc[trough_pk],
        trough_period=trough_pk,
        nwc_volatility=volatility,
        ratios=ratios,
    )


def _build_data_points(bs: BalanceSheet, pnl: PnLStatement | None) -> list[NWCDataPoint]:
    field_by_category = {
        CAT.ACCOUNTS_RECEIVABLE: "accounts_receivable",
        CAT.INVENTORY: "inventory",
        CAT.PREPAID_EXPENSES: "prepaid_expenses",
        CAT.OTHER_CURRENT_ASSETS: "other_current_assets",
        CAT.ACCOUNTS_PAYABLE: "accounts_payable",
        CAT.ACCRUED_LIABILITIES: "accrued_liabilities",
        CAT.DEFERRED_REVENUE: "deferred_revenue",
        CAT.CURRENT_DEBT: "current_debt",
        CAT.OTHER_CURRENT_LIABILITIES: "other_current_liabilities",
    }

    by_period: dict = defaultdict(lambda: defaultdict(Decimal))
    for row in bs.rows:
        try:
            cat = CAT(row.category)
        except ValueError:
            continue
        if cat not in NWC_COMPONENTS:
            continue
        field = field_by_category.get(cat)
        if field is None:
            continue
        by_period[row.period][field] += row.amount

    points: list[NWCDataPoint] = []
    for period in sorted(by_period.keys()):
        vals = by_period[period]
        assets_total = sum(
            (vals[f] for cat, f in field_by_category.items() if cat in _ASSET_CATEGORIES),
            Decimal("0"),
        )
        liab_total = sum(
            (vals[f] for cat, f in field_by_category.items() if cat in _LIABILITY_CATEGORIES),
            Decimal("0"),
        )
        nwc = assets_total - liab_total

        pct_rev = None
        if pnl is not None:
            pk = period.strftime("%Y-%m")
            rev = pnl.revenue.get(pk)
            if rev:
                pct_rev = float(nwc / rev)

        points.append(NWCDataPoint(
            period=period,
            accounts_receivable=vals.get("accounts_receivable", Decimal("0")),
            inventory=vals.get("inventory", Decimal("0")),
            prepaid_expenses=vals.get("prepaid_expenses", Decimal("0")),
            other_current_assets=vals.get("other_current_assets", Decimal("0")),
            accounts_payable=vals.get("accounts_payable", Decimal("0")),
            accrued_liabilities=vals.get("accrued_liabilities", Decimal("0")),
            deferred_revenue=vals.get("deferred_revenue", Decimal("0")),
            current_debt=vals.get("current_debt", Decimal("0")),
            other_current_liabilities=vals.get("other_current_liabilities", Decimal("0")),
            net_working_capital=nwc,
            nwc_as_pct_revenue=pct_rev,
        ))
    return points


def _compute_pegs(monthly_nwc: dict[str, Decimal]) -> list[NWCPeg]:
    sorted_periods = sorted(monthly_nwc.keys())
    values = [monthly_nwc[pk] for pk in sorted_periods]
    trailing12 = values[-12:] if len(values) >= 12 else values
    n_trailing = len(trailing12)

    trailing_floats = [float(v) for v in trailing12]
    ltm_mean = statistics.mean(trailing_floats)
    ltm_stdev = statistics.pstdev(trailing_floats) if n_trailing >= 2 else 0.0
    median_val = statistics.median(trailing_floats)
    median_stdev = ltm_stdev  # same sample; robustness differs in central tendency, not spread

    seasonal_peg = None
    seasonal_low = seasonal_high = None
    seasonality_detected = False
    seasonality_variation = 0.0

    if len(values) >= _MIN_MONTHS_FOR_SEASONALITY:
        month_groups: dict[int, list[float]] = defaultdict(list)
        for pk in sorted_periods:
            month = int(pk.split("-")[1])
            month_groups[month].append(float(monthly_nwc[pk]))
        monthly_avgs = {m: statistics.mean(v) for m, v in month_groups.items() if v}
        if monthly_avgs:
            seasonal_peg = statistics.mean(monthly_avgs.values())
            if seasonal_peg:
                seasonality_variation = (
                    max(monthly_avgs.values()) - min(monthly_avgs.values())
                ) / abs(seasonal_peg)
            seasonality_detected = seasonality_variation > _SEASONALITY_THRESHOLD
            seasonal_stdev = (
                statistics.pstdev(monthly_avgs.values()) if len(monthly_avgs) >= 2 else 0.0
            )
            seasonal_low = seasonal_peg - seasonal_stdev
            seasonal_high = seasonal_peg + seasonal_stdev

    # Recommendation logic
    outlier_skew = abs(ltm_mean - median_val) / abs(ltm_mean) if ltm_mean else 0.0
    if seasonal_peg is not None and seasonality_detected:
        recommended_method = "seasonal_adjusted"
    elif outlier_skew > _OUTLIER_SKEW_THRESHOLD:
        recommended_method = "median_trailing_12"
    else:
        recommended_method = "ltm_average"

    pegs = [
        NWCPeg(
            method="ltm_average",
            peg_amount=Decimal(str(round(ltm_mean, 2))),
            confidence_interval_low=Decimal(str(round(ltm_mean - ltm_stdev, 2))),
            confidence_interval_high=Decimal(str(round(ltm_mean + ltm_stdev, 2))),
            seasonality_detected=seasonality_detected,
            recommended=recommended_method == "ltm_average",
            rationale=(
                f"Simple average of the trailing {n_trailing} month(s) of NWC. Standard, "
                "transparent baseline used when the series shows no material outliers or seasonality."
            ),
        ),
        NWCPeg(
            method="median_trailing_12",
            peg_amount=Decimal(str(round(median_val, 2))),
            confidence_interval_low=Decimal(str(round(median_val - median_stdev, 2))),
            confidence_interval_high=Decimal(str(round(median_val + median_stdev, 2))),
            seasonality_detected=seasonality_detected,
            recommended=recommended_method == "median_trailing_12",
            rationale=(
                f"Median of the trailing {n_trailing} month(s) of NWC, robust to one-off spikes. "
                f"Mean vs. median diverge by {outlier_skew:.1%}, "
                + ("above" if outlier_skew > _OUTLIER_SKEW_THRESHOLD else "within")
                + f" the {_OUTLIER_SKEW_THRESHOLD:.0%} outlier-skew threshold."
            ),
        ),
    ]

    if seasonal_peg is not None:
        pegs.append(NWCPeg(
            method="seasonal_adjusted",
            peg_amount=Decimal(str(round(seasonal_peg, 2))),
            confidence_interval_low=Decimal(str(round(seasonal_low, 2))),
            confidence_interval_high=Decimal(str(round(seasonal_high, 2))),
            seasonality_detected=seasonality_detected,
            recommended=recommended_method == "seasonal_adjusted",
            rationale=(
                f"Average of same-calendar-month NWC across {len(values)} months of history "
                f"({seasonality_variation:.1%} spread between the highest and lowest average month), "
                + (
                    "which exceeds the 15% seasonality threshold — a plain trailing average would "
                    "misstate the peg depending on deal-close timing."
                    if seasonality_detected
                    else "within the 15% seasonality threshold, so this is offered as a cross-check only."
                )
            ),
        ))

    return pegs


def _compute_ratios(
    data_points: list[NWCDataPoint],
    pnl: PnLStatement | None,
    ar_aging: AgingReport | None,
    ap_aging: AgingReport | None,
) -> WorkingCapitalRatios | None:
    if not data_points:
        return None
    latest = data_points[-1]
    latest_pk = latest.period.strftime("%Y-%m")

    dso = dpo = dio = ccc = None
    if pnl is not None:
        revenue = pnl.revenue.get(latest_pk)
        gross_profit = pnl.gross_profit.get(latest_pk)
        cogs = (revenue - gross_profit) if (revenue is not None and gross_profit is not None) else None
        # cogs is a negative economic amount; use its magnitude for day-count ratios
        cogs_abs = abs(cogs) if cogs is not None else None

        if revenue:
            dso = float(latest.accounts_receivable / revenue) * 30
        if cogs_abs:
            dpo = float(latest.accounts_payable / cogs_abs) * 30
            dio = float(latest.inventory / cogs_abs) * 30
        if dso is not None and dio is not None and dpo is not None:
            ccc = dso + dio - dpo

    ar_over_60 = _latest_over_60_pct(ar_aging, latest.period)
    ap_over_60 = _latest_over_60_pct(ap_aging, latest.period)

    return WorkingCapitalRatios(
        period=latest_pk,
        dso_days=dso,
        dpo_days=dpo,
        dio_days=dio,
        cash_conversion_cycle_days=ccc,
        ar_over_60d_pct=ar_over_60,
        ap_over_60d_pct=ap_over_60,
    )


def _latest_over_60_pct(report: AgingReport | None, target_period) -> float | None:
    if report is None or not report.summaries:
        return None

    exact = [s for s in report.summaries if s.period == target_period]
    summary: AgingSummary = exact[0] if exact else max(report.summaries, key=lambda s: s.period)
    if not summary.total:
        return None

    over_60 = summary.bucket_61_90 + summary.bucket_90_plus
    return float(over_60 / summary.total) * 100


# ── Commercial health report ─────────────────────────────────────────────────

def _build_commercial_report(deal_id: str, pnl: PnLStatement | None) -> CommercialHealthReport:
    unavailable = [
        "customer_concentration_pct (requires customer-level revenue schedule)",
        "customer_count_trend (requires customer-level revenue schedule)",
        "customer_churn_proxy (requires customer-level revenue schedule)",
    ]

    if pnl is None:
        return CommercialHealthReport(
            deal_id=deal_id,
            status="skipped",
            message="P&L unavailable — commercial health requires the financial_builder stage to run first.",
            unavailable_metrics=unavailable,
        )

    revenue_by_period = {pk: float(v) for pk, v in pnl.revenue.items()}
    gm_by_period = {pk: v * 100 for pk, v in pnl.gross_margin.items()}
    em_by_period = {pk: v * 100 for pk, v in pnl.ebitda_margin.items()}

    # Annual revenue growth YoY
    annual_rev: dict[str, float] = defaultdict(float)
    for pk, rev in revenue_by_period.items():
        annual_rev[pk[:4]] += rev
    years = sorted(annual_rev.keys())
    growth_yoy = {
        years[i]: ((annual_rev[years[i]] / annual_rev[years[i - 1]]) - 1) * 100
        for i in range(1, len(years))
        if annual_rev[years[i - 1]]
    }

    values = list(revenue_by_period.values())
    volatility = None
    if len(values) >= 2:
        mean_val = statistics.mean(values)
        if mean_val:
            volatility = statistics.pstdev(values) / mean_val

    # Seasonality: Q4 revenue concentration vs. annual total (plan.txt rule: >40% flags seasonality)
    seasonality_detected = False
    seasonality_note = None
    q4_pcts = []
    for yr in years:
        yr_periods = [pk for pk in revenue_by_period if pk.startswith(yr)]
        q4_periods = [pk for pk in yr_periods if pk.split("-")[1] in ("10", "11", "12")]
        yr_total = sum(revenue_by_period[pk] for pk in yr_periods)
        if yr_total and len(yr_periods) == 12:
            q4_pcts.append(sum(revenue_by_period[pk] for pk in q4_periods) / yr_total)
    if q4_pcts:
        avg_q4_pct = statistics.mean(q4_pcts)
        if avg_q4_pct > 0.40:
            seasonality_detected = True
            seasonality_note = (
                f"Q4 revenue averages {avg_q4_pct:.0%} of annual revenue across "
                f"{len(q4_pcts)} full year(s), above the 40% concentration threshold."
            )
        else:
            seasonality_note = (
                f"Q4 revenue averages {avg_q4_pct:.0%} of annual revenue — within normal range."
            )

    return CommercialHealthReport(
        deal_id=deal_id,
        status="partial",
        message=(
            "Growth, margin, and volatility metrics computed from ingested financials. "
            "Customer-level metrics unavailable — see unavailable_metrics."
        ),
        revenue_growth_yoy_pct=growth_yoy,
        gross_margin_trend_pct=gm_by_period,
        ebitda_margin_trend_pct=em_by_period,
        revenue_volatility=volatility,
        seasonality_detected=seasonality_detected,
        seasonality_note=seasonality_note,
        unavailable_metrics=unavailable,
    )


def load_nwc_report(deal_id: str) -> NWCReport:
    p = _path(deal_id, "nwc_report.json")
    if not p.exists():
        raise FileNotFoundError(f"NWC report not found for deal {deal_id}. Run nwc_analyzer stage first.")
    with open(p, encoding="utf-8") as f:
        return NWCReport.model_validate(json.load(f))


def load_commercial_report(deal_id: str) -> CommercialHealthReport:
    p = _path(deal_id, "commercial_report.json")
    if not p.exists():
        raise FileNotFoundError(f"Commercial health report not found for deal {deal_id}. Run nwc_analyzer stage first.")
    with open(p, encoding="utf-8") as f:
        return CommercialHealthReport.model_validate(json.load(f))
