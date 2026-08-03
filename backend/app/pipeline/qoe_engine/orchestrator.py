"""
QoE Engine Orchestrator — coordinates: rules → LLM review → normalisation → persist.
"""

import asyncio
import logging
from pathlib import Path

from app.agents.qoe_reviewer import QoEReviewerAgent
from app.pipeline.financial_builder.orchestrator import FinancialBuilderError, load_mapped_gl
from app.pipeline.qoe_engine import normalizer, rules
from app.schemas.financials import PnLStatement
from app.schemas.qoe import QoEReport
from app.storage import file_store
from app.storage.json_io import read_json_encrypted, write_json_encrypted

logger = logging.getLogger(__name__)


def _path(deal_id: str, filename: str) -> Path:
    return file_store.get_processed_dir(deal_id) / filename


def _load_pnl(deal_id: str) -> PnLStatement:
    p = _path(deal_id, "financials_pnl.json")
    if not p.exists():
        raise FinancialBuilderError(f"P&L not found for deal {deal_id}. Run financial_builder first.")
    return PnLStatement.model_validate(read_json_encrypted(p))


def run(deal_id: str) -> QoEReport:
    return asyncio.run(_run_async(deal_id))


async def _run_async(deal_id: str) -> QoEReport:
    mapped_lines = load_mapped_gl(deal_id)
    pnl = _load_pnl(deal_id)

    # Step 1: deterministic rule detection
    candidates = rules.detect_all(mapped_lines, deal_id)
    logger.info("QoE rules: %d candidates detected", len(candidates))

    # Step 2: LLM review (mock or real)
    reviewer = QoEReviewerAgent()
    approved = await reviewer.review(candidates)
    logger.info("QoE review: %d adjustments approved", len(approved))

    # Step 3: build report (normalise EBITDA, build waterfall)
    report = normalizer.build_report(pnl, approved, deal_id)

    # Persist
    out = _path(deal_id, "qoe_report.json")
    write_json_encrypted(out, report.model_dump(mode="json"))

    return report


def load_qoe_report(deal_id: str) -> QoEReport:
    p = _path(deal_id, "qoe_report.json")
    if not p.exists():
        raise FileNotFoundError(f"QoE report not found for deal {deal_id}. Run qoe_engine stage first.")
    return QoEReport.model_validate(read_json_encrypted(p))
