"""
Pipeline Orchestrator — coordinates all processing stages for a deal.

Runs stages sequentially; status is updated in the deal store after each.
"""

import logging

from app.storage import deal_store

logger = logging.getLogger(__name__)

STAGE_ORDER = [
    "ingestion",
    "coa_mapping",
    "financial_builder",
    "qoe_engine",
    "redflag_detector",
    "nwc_analyzer",
    "dcf_engine",
    "net_debt_bridge",
]


def run(deal_id: str, stages: list[str]) -> None:
    """Entry point called as a FastAPI BackgroundTask."""
    logger.info("Pipeline started for deal %s | stages: %s", deal_id, stages)

    for stage in stages:
        if stage not in STAGE_ORDER:
            logger.warning("Unknown stage '%s' — skipping", stage)
            continue

        try:
            deal_store.set_stage_status(deal_id, stage, "running")
            logger.info("Stage '%s' started for deal %s", stage, deal_id)
            _run_stage(deal_id, stage)
            deal_store.set_stage_status(deal_id, stage, "complete")
            logger.info("Stage '%s' complete for deal %s", stage, deal_id)
        except Exception as exc:
            logger.exception("Stage '%s' failed for deal %s: %s", stage, deal_id, exc)
            deal_store.set_stage_status(deal_id, stage, "failed")
            deal_store.update_deal(deal_id, {"error": str(exc)})
            return

    logger.info("Pipeline complete for deal %s", deal_id)


def _run_stage(deal_id: str, stage: str) -> None:
    if stage == "ingestion":
        from app.pipeline.ingestion import orchestrator as ingestion_orch
        result = ingestion_orch.run(deal_id)
        report = result.validation_report
        logger.info(
            "Ingestion complete: %d GL lines, %d periods, balanced=%s, warnings=%d",
            len(result.gl_lines),
            report.periods_checked if report else 0,
            report.is_balanced if report else False,
            len(result.warnings),
        )

    elif stage == "coa_mapping":
        logger.info("coa_mapping is run as part of financial_builder — no-op here")

    elif stage == "financial_builder":
        from app.pipeline.financial_builder import orchestrator as fb_orch
        fb_orch.run(deal_id)

    elif stage == "qoe_engine":
        from app.pipeline.qoe_engine import orchestrator as qoe_orch
        qoe_orch.run(deal_id)

    elif stage == "redflag_detector":
        from app.pipeline.redflag_detector import orchestrator as rf_orch
        rf_orch.run(deal_id)

    elif stage == "nwc_analyzer":
        from app.pipeline.nwc_analyzer import orchestrator as nwc_orch
        nwc_orch.run(deal_id)

    elif stage == "dcf_engine":
        from app.pipeline.dcf_engine import orchestrator as dcf_orch
        dcf_orch.run(deal_id)

    elif stage == "net_debt_bridge":
        from app.pipeline.net_debt_bridge import orchestrator as nd_orch
        nd_orch.run(deal_id)
