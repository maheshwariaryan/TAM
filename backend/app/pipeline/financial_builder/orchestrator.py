"""
Financial Builder Orchestrator — runs CoA mapping then builds all three statements.

Stages in order:
  1. Extract unique (account_code, description) pairs from raw GL
  2. Call CoAMapperAgent to classify them (mock or real)
  3. Apply classifications → produce list[MappedGLLine]
  4. Build P&L, Balance Sheet, Cash Flow
  5. Persist all outputs to disk

Reads from:  data/processed/{deal_id}/raw_gl.json
Writes to:   data/processed/{deal_id}/mapped_gl.json
             data/processed/{deal_id}/financials_pnl.json
             data/processed/{deal_id}/financials_bs.json
             data/processed/{deal_id}/financials_cf.json
"""

import asyncio
import json
import logging
from pathlib import Path

from app.agents.coa_mapper import CoAMapperAgent
from app.pipeline.financial_builder import balance_sheet as bs_builder
from app.pipeline.financial_builder import cash_flow as cf_builder
from app.pipeline.financial_builder import pnl as pnl_builder
from app.pipeline.ingestion.orchestrator import IngestionError, load_raw_gl
from app.schemas.gl import (
    EBITDA_COMPONENTS,
    NWC_COMPONENTS,
    ChartOfAccountsCategory,
    MappedGLLine,
    RawGLLine,
)
from app.storage import file_store

logger = logging.getLogger(__name__)


class FinancialBuilderError(Exception):
    pass


def _processed_path(deal_id: str, filename: str) -> Path:
    return file_store.get_processed_dir(deal_id) / filename


def _save_json(path: Path, data: object) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def run(deal_id: str) -> None:
    """Synchronous entry point called by the orchestrator (runs in thread pool)."""
    asyncio.run(_run_async(deal_id))


async def _run_async(deal_id: str) -> None:
    # ── Step 1: Load raw GL ───────────────────────────────────────────────────
    try:
        raw_lines = load_raw_gl(deal_id)
    except IngestionError as exc:
        raise FinancialBuilderError(str(exc)) from exc

    logger.info("Loaded %d raw GL lines for deal %s", len(raw_lines), deal_id)

    # ── Step 2: CoA mapping ───────────────────────────────────────────────────
    unique_pairs = list({
        (line.account_code, line.account_description)
        for line in raw_lines
    })
    logger.info("Mapping %d unique accounts via CoAMapperAgent", len(unique_pairs))

    agent = CoAMapperAgent()
    classification_map = await agent.map_accounts(unique_pairs)

    # ── Step 3: Apply classifications → MappedGLLine ─────────────────────────
    mapped_lines = _apply_classifications(raw_lines, classification_map)
    logger.info("Produced %d mapped GL lines", len(mapped_lines))

    # Persist mapped GL
    _save_json(
        _processed_path(deal_id, "mapped_gl.json"),
        [gl.model_dump(mode="json") for gl in mapped_lines],
    )

    # ── Step 4: Build financial statements ────────────────────────────────────
    pnl = pnl_builder.build(mapped_lines)
    _save_json(_processed_path(deal_id, "financials_pnl.json"), pnl.model_dump(mode="json"))
    logger.info("P&L built: %d periods", len(pnl.periods))

    # Balance sheet (only if BS lines exist)
    bs_lines = [gl for gl in mapped_lines if gl.financial_statement == "BalanceSheet"]
    if bs_lines:
        bs = bs_builder.build(mapped_lines)
        _save_json(_processed_path(deal_id, "financials_bs.json"), bs.model_dump(mode="json"))

        cf = cf_builder.build(mapped_lines, pnl, bs)
        _save_json(_processed_path(deal_id, "financials_cf.json"), cf.model_dump(mode="json"))
        logger.info("Balance sheet and cash flow built")
    else:
        logger.warning("No balance sheet accounts mapped — skipping BS and CF statements")


def _apply_classifications(
    raw_lines: list[RawGLLine],
    classification_map: dict[str, dict],
) -> list[MappedGLLine]:
    """
    Join classification results onto raw GL lines.
    Unmapped accounts fall back to MEMO / Memo.
    """
    mapped: list[MappedGLLine] = []

    for line in raw_lines:
        cls = classification_map.get(line.account_code)

        if cls is None:
            logger.warning(
                "Account %s ('%s') not in classification map — defaulting to MEMO",
                line.account_code, line.account_description,
            )
            category = ChartOfAccountsCategory.MEMO
            stmt = "Memo"
            confidence = 0.0
            reasoning = "No classification returned by CoA mapper"
        else:
            category = cls["category"]
            stmt = cls["financial_statement"]
            confidence = cls["confidence"]
            reasoning = cls.get("reasoning", "")

        mapped.append(MappedGLLine(
            **line.model_dump(),
            standard_category=category,
            financial_statement=stmt,
            is_ebitda_component=category in EBITDA_COMPONENTS,
            is_nwc_component=category in NWC_COMPONENTS,
            mapping_confidence=confidence,
            mapping_source="rule" if reasoning.startswith("Mock") else
                           "llm" if confidence < 1.0 else "manual",
            mapping_reasoning=reasoning,
        ))

    return mapped


def load_mapped_gl(deal_id: str) -> list[MappedGLLine]:
    path = _processed_path(deal_id, "mapped_gl.json")
    if not path.exists():
        raise FinancialBuilderError(
            f"No mapped GL found for deal {deal_id}. Run coa_mapping + financial_builder stages first."
        )
    with open(path, encoding="utf-8") as f:
        return [MappedGLLine.model_validate(item) for item in json.load(f)]
