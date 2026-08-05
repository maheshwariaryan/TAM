"""GET /api/v1/deals/{deal_id}/dcf — simple DCF cross-check (see schemas/dcf.py for scope)."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import require_deal_owner
from app.pipeline.dcf_engine.orchestrator import load_dcf_report
from app.schemas.dcf import DCFReport

router = APIRouter(tags=["DCF"])


@router.get("/deals/{deal_id}/dcf", response_model=DCFReport)
def get_dcf(deal_id: str, _owned_deal: dict = Depends(require_deal_owner)) -> DCFReport:
    try:
        return load_dcf_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
