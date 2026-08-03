"""Document inventory API."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import get_current_user, require_deal_owner
from app.pipeline.ingestion.orchestrator import IngestionError, load_document_inventory, load_supporting_schedules
from app.schemas.documents import DocumentInventory
from app.security.access_log import log_document_access

router = APIRouter(tags=["Documents"])


@router.get("/deals/{deal_id}/documents", response_model=DocumentInventory)
def get_document_inventory(
    deal: dict = Depends(require_deal_owner), current_user: dict = Depends(get_current_user)
) -> DocumentInventory:
    inventory = load_document_inventory(deal["deal_id"])
    log_document_access(
        user_id=current_user["id"], deal_id=deal["deal_id"], action="list_documents",
    )
    return inventory


@router.get("/deals/{deal_id}/supporting-schedules")
def get_supporting_schedules(
    deal: dict = Depends(require_deal_owner), current_user: dict = Depends(get_current_user)
) -> dict[str, list[dict]]:
    """Raw parsed tables for lease/fixed-asset/equity/payroll/bank-statement uploads —
    recognized and viewable, but not analyzed by any pipeline stage (see DocumentType
    docstring's Group C)."""
    try:
        schedules = load_supporting_schedules(deal["deal_id"])
    except IngestionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log_document_access(
        user_id=current_user["id"], deal_id=deal["deal_id"], action="list_supporting_schedules",
    )
    return schedules
