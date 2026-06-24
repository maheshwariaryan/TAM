"""Document inventory API."""

from fastapi import APIRouter, HTTPException

from app.pipeline.ingestion.orchestrator import load_document_inventory
from app.schemas.documents import DocumentInventory
from app.storage import deal_store

router = APIRouter(tags=["Documents"])


@router.get("/deals/{deal_id}/documents", response_model=DocumentInventory)
def get_document_inventory(deal_id: str) -> DocumentInventory:
    deal = deal_store.get_deal(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return load_document_inventory(deal_id)
