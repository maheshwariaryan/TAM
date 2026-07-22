"""
Narrative Drafter Orchestrator — builds a fact sheet of already-computed
figures from the QoE, red flag, NWC, and net debt reports, then hands it to
the NarrativeDrafterAgent for prose. No arithmetic happens here beyond
formatting Decimals/floats as display strings; every figure traces back to
the report it was read from (see `figures_used` on the persisted report).

Can run as the final pipeline stage (after qoe_engine, redflag_detector,
nwc_analyzer, net_debt_bridge all have output) or be re-triggered on demand
via POST /deals/{id}/narrative/generate, e.g. after an analyst approves an
adjustment or a new document is uploaded.
"""

import asyncio
import json
import logging
from decimal import Decimal
from pathlib import Path

from app.agents.narrative_drafter import NarrativeDrafterAgent
from app.schemas.financials import PnLStatement
from app.schemas.narrative import NarrativeReport, NarrativeSection
from app.schemas.net_debt import NetDebtReport
from app.schemas.nwc import NWCReport
from app.schemas.qoe import QoEReport
from app.schemas.redflags import RedFlagReport
from app.storage import file_store

logger = logging.getLogger(__name__)


class NarrativeDrafterError(Exception):
    pass


def _path(deal_id: str, filename: str) -> Path:
    return file_store.get_processed_dir(deal_id) / filename


def _try_load(deal_id: str, filename: str, model_class):
    p = _path(deal_id, filename)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return model_class.model_validate(json.load(f))


def _money(amount: Decimal) -> str:
    return f"${float(amount):,.0f}"


def _pct(value: float) -> str:
    return f"{value:.1%}"


def _multiple(value: float) -> str:
    return f"{value:.2f}x"


def run(deal_id: str) -> NarrativeReport:
    return asyncio.run(_run_async(deal_id))


async def _run_async(deal_id: str) -> NarrativeReport:
    pnl = _try_load(deal_id, "financials_pnl.json", PnLStatement)
    qoe = _try_load(deal_id, "qoe_report.json", QoEReport)
    redflags = _try_load(deal_id, "redflag_report.json", RedFlagReport)
    nwc = _try_load(deal_id, "nwc_report.json", NWCReport)
    net_debt = _try_load(deal_id, "net_debt_report.json", NetDebtReport)

    if pnl is None or qoe is None:
        report = NarrativeReport(
            deal_id=deal_id,
            status="skipped",
            message=(
                "Narrative requires the financial_builder and qoe_engine stages to complete "
                "first — run /process before generating a narrative."
            ),
        )
        _persist(deal_id, report)
        return report

    figures, data_gaps = _build_fact_sheet(pnl, qoe, redflags, nwc, net_debt)

    agent = NarrativeDrafterAgent()
    result = await agent.run(figures)
    sections = [NarrativeSection.model_validate(s) for s in result.get("sections", [])]

    status = "complete" if not data_gaps else "partial"
    message = (
        "Narrative drafted from all available reports."
        if status == "complete"
        else f"Narrative drafted; some inputs were unavailable: {', '.join(data_gaps)}."
    )

    report = NarrativeReport(
        deal_id=deal_id,
        status=status,
        message=message,
        sections=sections,
        figures_used=figures,
        data_gaps=data_gaps,
    )
    _persist(deal_id, report)
    logger.info("Narrative drafted for %s: status=%s, %d section(s)", deal_id, status, len(sections))
    return report


def _build_fact_sheet(
    pnl: PnLStatement,
    qoe: QoEReport,
    redflags: RedFlagReport | None,
    nwc: NWCReport | None,
    net_debt: NetDebtReport | None,
) -> tuple[dict[str, str], list[str]]:
    figures: dict[str, str] = {}
    data_gaps: list[str] = []

    sorted_periods = sorted(pnl.revenue.keys())
    trailing12 = sorted_periods[-12:] if len(sorted_periods) >= 12 else sorted_periods
    revenue_ltm = sum((pnl.revenue[p] for p in trailing12), Decimal("0"))
    figures["revenue_ltm"] = _money(revenue_ltm)

    figures["reported_ebitda_ltm"] = _money(qoe.ltm_reported)
    figures["adjusted_ebitda_ltm"] = _money(qoe.ltm_adjusted)
    figures["qoe_adjustment_count"] = str(qoe.adjustment_count)
    figures["qoe_categories"] = ", ".join(qoe.categories_adjusted) if qoe.categories_adjusted else "none"
    if revenue_ltm:
        figures["ebitda_margin_pct"] = _pct(float(qoe.ltm_reported / revenue_ltm))
    if qoe.ltm_reported:
        figures["adjustment_pct"] = _pct(float(qoe.ltm_adjustment_total / qoe.ltm_reported))

    if redflags is not None:
        figures["redflag_high_count"] = str(redflags.summary.high)
        figures["redflag_medium_count"] = str(redflags.summary.medium)
        top_flags = [f for f in redflags.flags if f.severity in ("High", "Medium")][:3]
        figures["top_flags"] = "; ".join(f.title for f in top_flags) if top_flags else "none identified"
        questions = [f.diligence_questions[0] for f in top_flags if f.diligence_questions]
        figures["diligence_questions"] = " | ".join(questions) if questions else "none outstanding"
    else:
        data_gaps.append("red flags")

    if nwc is not None and nwc.pegs:
        recommended = next((p for p in nwc.pegs if p.recommended), nwc.pegs[0])
        figures["nwc_peg_amount"] = _money(recommended.peg_amount)
        figures["nwc_peg_method"] = recommended.method
    else:
        data_gaps.append("NWC peg")

    if net_debt is not None and net_debt.net_debt is not None:
        figures["net_debt"] = _money(net_debt.net_debt)
        if net_debt.net_debt_to_ebitda is not None:
            figures["net_debt_to_ebitda"] = _multiple(net_debt.net_debt_to_ebitda)
    else:
        data_gaps.append("net debt bridge")

    return figures, data_gaps


def _persist(deal_id: str, report: NarrativeReport) -> None:
    out = _path(deal_id, "narrative_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(mode="json"), f, indent=2, default=str)


def load_narrative_report(deal_id: str) -> NarrativeReport:
    p = _path(deal_id, "narrative_report.json")
    if not p.exists():
        raise FileNotFoundError(
            f"No narrative report found for deal {deal_id}. POST /narrative/generate first."
        )
    with open(p, encoding="utf-8") as f:
        return NarrativeReport.model_validate(json.load(f))
