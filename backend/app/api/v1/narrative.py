"""
Narrative report API endpoints.

POST /api/v1/deals/{deal_id}/narrative/generate   (Re-)draft narrative sections
GET  /api/v1/deals/{deal_id}/narrative            Fetch the persisted narrative
"""

from fastapi import APIRouter, HTTPException

from app.pipeline.narrative.orchestrator import load_narrative_report
from app.pipeline.narrative.orchestrator import run as run_narrative
from app.schemas.narrative import NarrativeReport
from app.storage import deal_store

router = APIRouter(tags=["Narrative"])


@router.post("/deals/{deal_id}/narrative/generate", response_model=NarrativeReport)
def generate_narrative(deal_id: str) -> NarrativeReport:
    deal = deal_store.get_deal(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return run_narrative(deal_id)


@router.get("/deals/{deal_id}/narrative", response_model=NarrativeReport)
def get_narrative(deal_id: str) -> NarrativeReport:
    try:
        return load_narrative_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
