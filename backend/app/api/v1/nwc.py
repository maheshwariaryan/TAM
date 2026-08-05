"""
NWC + Commercial Health API endpoints.

GET /api/v1/deals/{deal_id}/nwc          Net working capital trend + peg + ratios
GET /api/v1/deals/{deal_id}/commercial   Commercial health metrics
"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import require_deal_owner
from app.pipeline.nwc_analyzer.orchestrator import load_commercial_report, load_nwc_report
from app.schemas.nwc import CommercialHealthReport, NWCReport

router = APIRouter(tags=["Working Capital"])


@router.get("/deals/{deal_id}/nwc", response_model=NWCReport)
def get_nwc(deal_id: str, _owned_deal: dict = Depends(require_deal_owner)) -> NWCReport:
    try:
        return load_nwc_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/deals/{deal_id}/commercial", response_model=CommercialHealthReport)
def get_commercial(deal_id: str, _owned_deal: dict = Depends(require_deal_owner)) -> CommercialHealthReport:
    try:
        return load_commercial_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
