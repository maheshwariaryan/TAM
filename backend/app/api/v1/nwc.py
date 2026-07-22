"""
NWC + Commercial Health API endpoints.

GET /api/v1/deals/{deal_id}/nwc          Net working capital trend + peg + ratios
GET /api/v1/deals/{deal_id}/commercial   Commercial health metrics
"""

from fastapi import APIRouter, HTTPException

from app.pipeline.nwc_analyzer.orchestrator import load_commercial_report, load_nwc_report
from app.schemas.nwc import CommercialHealthReport, NWCReport

router = APIRouter(tags=["Working Capital"])


@router.get("/deals/{deal_id}/nwc", response_model=NWCReport)
def get_nwc(deal_id: str) -> NWCReport:
    try:
        return load_nwc_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/deals/{deal_id}/commercial", response_model=CommercialHealthReport)
def get_commercial(deal_id: str) -> CommercialHealthReport:
    try:
        return load_commercial_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
