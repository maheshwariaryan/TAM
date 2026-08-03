"""
DCF Engine — simple, auditable discounted cash flow from management projections.

Deliberately not a "fancy" model: unlevered FCF = EBITDA - Capex per projected
period (no tax or NWC-change adjustment), discounted monthly at a disclosed
default annual rate, with a Gordon-growth terminal value on the final period.
All arithmetic is Python/Decimal; the discount rate and growth rate are
labeled assumptions, not computed outputs, and every simplification is listed
in `limitations` — see schemas/dcf.py for why. Prefer the net debt bridge and
NWC peg for headline deal metrics; this is a directional cross-check only.
"""

import logging
from decimal import Decimal
from pathlib import Path

from app.schemas.dcf import DCFAssumptions, DCFReport
from app.schemas.projections import ProjectionSchedule
from app.storage import file_store
from app.storage.json_io import read_json_encrypted, write_json_encrypted

logger = logging.getLogger(__name__)

DEFAULT_DISCOUNT_RATE_ANNUAL = 0.12
DEFAULT_TERMINAL_GROWTH_ANNUAL = 0.02

_LIMITATIONS = [
    "Unlevered FCF approximated as EBITDA - Capex; excludes taxes and changes in net working capital.",
    "Discount rate is a disclosed default assumption (12% annual), not a deal-specific WACC — "
    "this system has no capital structure or cost-of-capital inputs to derive one from.",
    "Terminal value uses a disclosed default 2% perpetuity growth rate on the final projected period.",
    "Directional cross-check only — prefer the net debt bridge and NWC peg for headline deal metrics.",
]


class DCFEngineError(Exception):
    pass


def _path(deal_id: str, filename: str) -> Path:
    return file_store.get_processed_dir(deal_id) / filename


def run(deal_id: str) -> dict:
    proj_path = _path(deal_id, "management_projections.json")

    if not proj_path.exists():
        report = DCFReport(
            deal_id=deal_id,
            status="skipped",
            message="Management projections not uploaded — DCF skipped. Upload projections to enable.",
        )
    else:
        try:
            schedule = ProjectionSchedule.model_validate(read_json_encrypted(proj_path))
        except Exception as exc:
            logger.exception("DCF engine: management_projections.json is corrupted for deal %s", deal_id)
            report = DCFReport(
                deal_id=deal_id,
                status="failed",
                message=f"Could not read management_projections.json: {exc}",
            )
        else:
            report = _build_report(deal_id, schedule)

    out = _path(deal_id, "dcf_report.json")
    write_json_encrypted(out, report.model_dump(mode="json"))

    logger.info("DCF engine complete for %s (status=%s)", deal_id, report.status)
    return report.model_dump(mode="json")


def _build_report(deal_id: str, schedule: ProjectionSchedule) -> DCFReport:
    lines = sorted(schedule.lines, key=lambda ln: ln.period)
    if not lines:
        return DCFReport(
            deal_id=deal_id,
            status="skipped",
            message="Projection file contained no periods.",
        )

    fcf_by_period: dict[str, Decimal] = {}
    for line in lines:
        pk = line.period.strftime("%Y-%m")
        ebitda = line.ebitda
        if ebitda is None and line.revenue is not None and line.cogs is not None and line.opex is not None:
            # cogs/opex are stored as positive expense magnitudes (see projections_parser.py's
            # identical fallback) — must subtract, not add.
            ebitda = line.revenue - line.cogs - line.opex
        if ebitda is None:
            continue
        capex = line.capex or Decimal("0")
        fcf_by_period[pk] = ebitda - capex

    if not fcf_by_period:
        return DCFReport(
            deal_id=deal_id,
            status="skipped",
            message="Projections contained no EBITDA (directly or via revenue/COGS/opex) to build FCF.",
        )

    monthly_rate = (1 + DEFAULT_DISCOUNT_RATE_ANNUAL) ** (1 / 12) - 1
    periods_sorted = sorted(fcf_by_period.keys())

    pv_by_period: dict[str, Decimal] = {}
    for month_idx, pk in enumerate(periods_sorted, start=1):
        discount_factor = Decimal(str((1 + monthly_rate) ** -month_idx))
        pv_by_period[pk] = (fcf_by_period[pk] * discount_factor).quantize(Decimal("0.01"))

    sum_pv = sum(pv_by_period.values(), Decimal("0"))

    # Terminal value: annualize the final period's FCF, apply Gordon growth, discount back.
    final_month_fcf = fcf_by_period[periods_sorted[-1]]
    annualized_final_fcf = final_month_fcf * 12
    terminal_value = (
        annualized_final_fcf * Decimal(str(1 + DEFAULT_TERMINAL_GROWTH_ANNUAL))
        / Decimal(str(DEFAULT_DISCOUNT_RATE_ANNUAL - DEFAULT_TERMINAL_GROWTH_ANNUAL))
    )
    final_discount_factor = Decimal(str((1 + monthly_rate) ** -len(periods_sorted)))
    pv_terminal = (terminal_value * final_discount_factor).quantize(Decimal("0.01"))

    enterprise_value = (sum_pv + pv_terminal).quantize(Decimal("0.01"))

    return DCFReport(
        deal_id=deal_id,
        status="complete",
        message=f"Simple DCF computed from {len(periods_sorted)} projected month(s).",
        projection_periods=len(periods_sorted),
        assumptions=DCFAssumptions(
            discount_rate_annual=DEFAULT_DISCOUNT_RATE_ANNUAL,
            terminal_growth_rate_annual=DEFAULT_TERMINAL_GROWTH_ANNUAL,
        ),
        projected_fcf=fcf_by_period,
        pv_of_fcf=pv_by_period,
        sum_pv_of_fcf=sum_pv.quantize(Decimal("0.01")),
        terminal_value=terminal_value.quantize(Decimal("0.01")),
        pv_of_terminal_value=pv_terminal,
        enterprise_value=enterprise_value,
        limitations=_LIMITATIONS,
    )


def load_dcf_report(deal_id: str) -> DCFReport:
    p = _path(deal_id, "dcf_report.json")
    if not p.exists():
        raise FileNotFoundError(f"DCF report not found for deal {deal_id}. Run dcf_engine stage first.")
    return DCFReport.model_validate(read_json_encrypted(p))
