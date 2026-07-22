"""GET /api/v1/deals/{deal_id}/tie-outs — cross-document reconciliation (AR/AP aging vs. GL)."""

import json

from fastapi import APIRouter, HTTPException

from app.schemas.aging import CrossDocumentValidation
from app.storage import file_store

router = APIRouter(tags=["Tie-Outs"])


@router.get("/deals/{deal_id}/tie-outs", response_model=CrossDocumentValidation)
def get_tie_outs(deal_id: str) -> CrossDocumentValidation:
    path = file_store.get_processed_dir(deal_id) / "cross_document_validation.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Tie-out results not found for deal {deal_id}. Run the ingestion stage first.",
        )
    with open(path, encoding="utf-8") as f:
        return CrossDocumentValidation.model_validate(json.load(f))
