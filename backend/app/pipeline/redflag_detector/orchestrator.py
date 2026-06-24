"""
Red Flag Detector Orchestrator — rules → LLM enrichment → persist.
"""

import asyncio
import json
import logging
from pathlib import Path

from app.agents.redflag_analyst import RedFlagAnalystAgent
from app.pipeline.financial_builder.orchestrator import load_mapped_gl
from app.pipeline.qoe_engine.orchestrator import load_qoe_report
from app.pipeline.redflag_detector import rules
from app.schemas.financials import BalanceSheet, CashFlowStatement, PnLStatement
from app.schemas.redflags import RedFlagReport, RedFlagSummary
from app.storage import file_store

logger = logging.getLogger(__name__)


def _path(deal_id: str, filename: str) -> Path:
    return file_store.get_processed_dir(deal_id) / filename


def _try_load(deal_id: str, filename: str, model_class):
    p = _path(deal_id, filename)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return model_class.model_validate(json.load(f))


def run(deal_id: str) -> RedFlagReport:
    return asyncio.run(_run_async(deal_id))


async def _run_async(deal_id: str) -> RedFlagReport:
    mapped_lines = load_mapped_gl(deal_id)
    pnl: PnLStatement = _try_load(deal_id, "financials_pnl.json", PnLStatement)
    bs: BalanceSheet | None = _try_load(deal_id, "financials_bs.json", BalanceSheet)
    cf: CashFlowStatement | None = _try_load(deal_id, "financials_cf.json", CashFlowStatement)
    qoe = load_qoe_report(deal_id)

    if pnl is None:
        raise FileNotFoundError(f"P&L not found for deal {deal_id}.")

    # Step 1: deterministic rules
    all_flags = rules.detect_all(
        deal_id=deal_id,
        pnl=pnl,
        mapped_lines=mapped_lines,
        qoe=qoe,
        balance_sheet=bs,
        cash_flow=cf,
    )

    # Step 2: LLM enrichment — only High and Medium (cost control)
    analyst = RedFlagAnalystAgent()
    to_enrich = [f for f in all_flags if f.severity in ("High", "Medium")]
    low_flags = [f for f in all_flags if f.severity not in ("High", "Medium")]

    enriched = await analyst.enrich(to_enrich)
    final_flags = enriched + low_flags

    # Sort: High → Medium → Low → Informational
    order = {"High": 0, "Medium": 1, "Low": 2, "Informational": 3}
    final_flags.sort(key=lambda f: order.get(f.severity, 4))

    summary = RedFlagSummary(
        high=sum(1 for f in final_flags if f.severity == "High"),
        medium=sum(1 for f in final_flags if f.severity == "Medium"),
        low=sum(1 for f in final_flags if f.severity == "Low"),
        informational=sum(1 for f in final_flags if f.severity == "Informational"),
        total=len(final_flags),
    )

    report = RedFlagReport(deal_id=deal_id, flags=final_flags, summary=summary)

    out = _path(deal_id, "redflag_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(mode="json"), f, indent=2, default=str)

    logger.info(
        "Red flag report saved: High=%d Medium=%d Low=%d Info=%d",
        summary.high, summary.medium, summary.low, summary.informational,
    )
    return report


def load_redflag_report(deal_id: str) -> RedFlagReport:
    p = _path(deal_id, "redflag_report.json")
    if not p.exists():
        raise FileNotFoundError(f"Red flag report not found for deal {deal_id}.")
    with open(p, encoding="utf-8") as f:
        return RedFlagReport.model_validate(json.load(f))
