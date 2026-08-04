"""
Red Flag Detector Orchestrator — rules → LLM enrichment → persist.
"""

import asyncio
import logging
from pathlib import Path

from app.agents.redflag_analyst import RedFlagAnalystAgent
from app.pipeline.financial_builder.orchestrator import load_mapped_gl
from app.pipeline.qoe_engine.orchestrator import load_qoe_report
from app.pipeline.redflag_detector import rules
from app.schemas.aging import CrossDocumentValidation
from app.schemas.financials import BalanceSheet, CashFlowStatement, PnLStatement
from app.schemas.net_debt import NetDebtReport
from app.schemas.nwc import NWCReport
from app.schemas.redflags import RedFlagReport, RedFlagSummary
from app.schemas.settings import get_deal_settings
from app.storage import deal_store, file_store
from app.storage.json_io import read_json_encrypted, write_json_encrypted

logger = logging.getLogger(__name__)


def _path(deal_id: str, filename: str) -> Path:
    return file_store.get_processed_dir(deal_id) / filename


def _try_load(deal_id: str, filename: str, model_class):
    p = _path(deal_id, filename)
    if not p.exists():
        return None
    return model_class.model_validate(read_json_encrypted(p))


def run(deal_id: str) -> RedFlagReport:
    return asyncio.run(_run_async(deal_id))


async def _run_async(deal_id: str) -> RedFlagReport:
    mapped_lines = load_mapped_gl(deal_id)
    pnl: PnLStatement = _try_load(deal_id, "financials_pnl.json", PnLStatement)
    bs: BalanceSheet | None = _try_load(deal_id, "financials_bs.json", BalanceSheet)
    cf: CashFlowStatement | None = _try_load(deal_id, "financials_cf.json", CashFlowStatement)
    nwc: NWCReport | None = _try_load(deal_id, "nwc_report.json", NWCReport)
    cross_validation: CrossDocumentValidation | None = _try_load(
        deal_id, "cross_document_validation.json", CrossDocumentValidation
    )
    net_debt_report: NetDebtReport | None = _try_load(deal_id, "net_debt_report.json", NetDebtReport)
    qoe = load_qoe_report(deal_id)

    if pnl is None:
        raise FileNotFoundError(f"P&L not found for deal {deal_id}.")

    # Step 1: deterministic rules
    deal_settings = get_deal_settings(deal_store.get_deal(deal_id))
    all_flags = rules.detect_all(
        deal_id=deal_id,
        pnl=pnl,
        mapped_lines=mapped_lines,
        qoe=qoe,
        balance_sheet=bs,
        cash_flow=cf,
        nwc_report=nwc,
        cross_validation=cross_validation,
        net_debt_report=net_debt_report,
        materiality_threshold=deal_settings.materiality_threshold,
        cash_conversion_medium_pct=deal_settings.cash_conversion_medium_pct,
        cash_conversion_high_pct=deal_settings.cash_conversion_high_pct,
        cash_conversion_critical_pct=deal_settings.cash_conversion_critical_pct,
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
    write_json_encrypted(out, report.model_dump(mode="json"))

    logger.info(
        "Red flag report saved: High=%d Medium=%d Low=%d Info=%d",
        summary.high, summary.medium, summary.low, summary.informational,
    )
    return report


def load_redflag_report(deal_id: str) -> RedFlagReport:
    p = _path(deal_id, "redflag_report.json")
    if not p.exists():
        raise FileNotFoundError(f"Red flag report not found for deal {deal_id}.")
    return RedFlagReport.model_validate(read_json_encrypted(p))
