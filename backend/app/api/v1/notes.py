"""
Deal-scoped analyst notes API endpoints.

GET /api/v1/deals/{deal_id}/notes   Fetch saved notes (empty defaults if none yet)
PUT /api/v1/deals/{deal_id}/notes   Full replace
"""

from fastapi import APIRouter, Depends

from app.api.v1.deps import require_deal_owner
from app.schemas.notes import DealNotes, DealNotesUpdate
from app.storage import note_store

router = APIRouter(tags=["Notes"])


@router.get("/deals/{deal_id}/notes", response_model=DealNotes)
def get_notes(deal: dict = Depends(require_deal_owner)) -> DealNotes:
    return note_store.get_notes(deal["deal_id"])


@router.put("/deals/{deal_id}/notes", response_model=DealNotes)
def save_notes(body: DealNotesUpdate, deal: dict = Depends(require_deal_owner)) -> DealNotes:
    return note_store.save_notes(deal["deal_id"], body.notes, body.report_draft)
