"""
Contract analysis API endpoints.

POST /api/v1/deals/{deal_id}/contracts/analyze   (Re-)run contract clause extraction
GET  /api/v1/deals/{deal_id}/contracts           Instruments + clause listing
"""

from fastapi import APIRouter, HTTPException

from app.pipeline.contracts.orchestrator import load_contract_analysis
from app.pipeline.contracts.orchestrator import run as run_contract_analysis
from app.schemas.contracts import ContractAnalysisReport
from app.storage import deal_store

router = APIRouter(tags=["Contracts"])


@router.post("/deals/{deal_id}/contracts/analyze", response_model=ContractAnalysisReport)
def analyze_contracts(deal_id: str) -> ContractAnalysisReport:
    deal = deal_store.get_deal(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return run_contract_analysis(deal_id)


@router.get("/deals/{deal_id}/contracts", response_model=ContractAnalysisReport)
def get_contracts(deal_id: str) -> ContractAnalysisReport:
    try:
        return load_contract_analysis(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
