"""GET /api/v1/deals/{deal_id}/dcf — simple DCF cross-check (see schemas/dcf.py for scope)."""

from fastapi import APIRouter, HTTPException

from app.pipeline.dcf_engine.orchestrator import load_dcf_report
from app.schemas.dcf import DCFReport

router = APIRouter(tags=["DCF"])


@router.get("/deals/{deal_id}/dcf", response_model=DCFReport)
def get_dcf(deal_id: str) -> DCFReport:
    try:
        return load_dcf_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
