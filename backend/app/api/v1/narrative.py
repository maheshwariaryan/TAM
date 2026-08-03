"""
Narrative report API endpoints.

POST /api/v1/deals/{deal_id}/narrative/generate   (Re-)draft narrative sections
GET  /api/v1/deals/{deal_id}/narrative            Fetch the persisted narrative
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.agents.base import AgentError
from app.api.v1.deps import require_deal_owner
from app.pipeline.narrative.orchestrator import load_narrative_report
from app.pipeline.narrative.orchestrator import run as run_narrative
from app.schemas.narrative import NarrativeReport

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Narrative"])


@router.post("/deals/{deal_id}/narrative/generate", response_model=NarrativeReport)
def generate_narrative(deal: dict = Depends(require_deal_owner)) -> NarrativeReport:
    deal_id = deal["deal_id"]
    try:
        return run_narrative(deal_id)
    except AgentError as exc:
        logger.exception("Narrative drafting LLM call failed for deal %s", deal_id)
        raise HTTPException(
            status_code=502, detail=f"LLM call failed during narrative drafting: {exc}"
        ) from exc


@router.get("/deals/{deal_id}/narrative", response_model=NarrativeReport)
def get_narrative(deal_id: str, _owned_deal: dict = Depends(require_deal_owner)) -> NarrativeReport:
    try:
        return load_narrative_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
