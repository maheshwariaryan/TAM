"""
Contract analysis API endpoints.

POST /api/v1/deals/{deal_id}/contracts/analyze   (Re-)run contract clause extraction
GET  /api/v1/deals/{deal_id}/contracts           Instruments + clause listing
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.agents.base import AgentError
from app.api.v1.deps import require_deal_owner
from app.pipeline.contracts.orchestrator import load_contract_analysis
from app.pipeline.contracts.orchestrator import run as run_contract_analysis
from app.schemas.contracts import ContractAnalysisReport

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Contracts"])


@router.post("/deals/{deal_id}/contracts/analyze", response_model=ContractAnalysisReport)
def analyze_contracts(deal: dict = Depends(require_deal_owner)) -> ContractAnalysisReport:
    deal_id = deal["deal_id"]
    try:
        return run_contract_analysis(deal_id)
    except AgentError as exc:
        logger.exception("Contract analysis LLM call failed for deal %s", deal_id)
        raise HTTPException(
            status_code=502, detail=f"LLM call failed during contract analysis: {exc}"
        ) from exc


@router.get("/deals/{deal_id}/contracts", response_model=ContractAnalysisReport)
def get_contracts(deal_id: str, _owned_deal: dict = Depends(require_deal_owner)) -> ContractAnalysisReport:
    try:
        return load_contract_analysis(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
