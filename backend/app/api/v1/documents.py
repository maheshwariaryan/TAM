"""Document inventory API."""

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user, require_deal_owner
from app.pipeline.ingestion.orchestrator import load_document_inventory
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
