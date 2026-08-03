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
    "nwc_analyzer",
    "net_debt_bridge",
    "redflag_detector",
    "dcf_engine",
    "narrative_drafter",
]


def run(deal_id: str, stages: list[str]) -> None:
    """
    Entry point called as a FastAPI BackgroundTask.

    This runs after the triggering HTTP response has already been sent (BackgroundTasks
    execute post-response), so nothing here can ever change that response — the only way
    the caller learns what happened is via deal_store (polled through /status). That makes
    this function the last line of defense: every branch below is deliberately paranoid
    about recording *something* readable, even if the recording itself fails, because a
    silent hang here is invisible to both the terminal and the client.
    """
    logger.info("Pipeline started for deal %s | stages: %s", deal_id, stages)

    try:
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
                _record_failure(deal_id, stage, str(exc))
                return
    except Exception as exc:
        # Anything not already caught above (e.g. a bug in this loop itself) — this is
        # the absolute last resort before the deal would otherwise sit at "running"
        # forever with no error ever recorded and no way for the client to find out.
        logger.exception("Pipeline crashed unexpectedly for deal %s: %s", deal_id, exc)
        _record_failure(deal_id, "unknown", str(exc))
        return

    logger.info("Pipeline complete for deal %s", deal_id)


def _record_failure(deal_id: str, stage: str, error: str) -> None:
    """Best-effort failure recording. If deal_store itself is the thing that's broken
    (corrupted deal file, disk issue), log loudly rather than let a secondary exception
    here mask the original failure and leave the deal silently stuck at 'running'."""
    try:
        deal_store.set_stage_status(deal_id, stage, "failed")
        deal_store.update_deal(deal_id, {"error": error})
    except Exception as exc:
        logger.exception(
            "Failed to record pipeline failure for deal %s (stage=%s, original_error=%r): %s — "
            "this deal may now be stuck showing an incomplete status; check the deal file directly.",
            deal_id, stage, error, exc,
        )


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

    elif stage == "narrative_drafter":
        from app.pipeline.narrative import orchestrator as narrative_orch
        narrative_orch.run(deal_id)
