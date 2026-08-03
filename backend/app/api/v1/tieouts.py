"""GET /api/v1/deals/{deal_id}/tie-outs — cross-document reconciliation (AR/AP aging vs. GL)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import require_deal_owner
from app.schemas.aging import CrossDocumentValidation
from app.storage import file_store
from app.storage.json_io import read_json_encrypted

router = APIRouter(tags=["Tie-Outs"])


@router.get("/deals/{deal_id}/tie-outs", response_model=CrossDocumentValidation)
def get_tie_outs(deal_id: str, _owned_deal: dict = Depends(require_deal_owner)) -> CrossDocumentValidation:
    path = file_store.get_processed_dir(deal_id) / "cross_document_validation.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Tie-out results not found for deal {deal_id}. Run the ingestion stage first.",
        )
    return CrossDocumentValidation.model_validate(read_json_encrypted(path))
