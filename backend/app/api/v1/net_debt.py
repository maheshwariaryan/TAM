"""GET /api/v1/deals/{deal_id}/net-debt — net debt bridge + instrument detail."""

from fastapi import APIRouter, HTTPException

from app.pipeline.net_debt_bridge.orchestrator import load_net_debt_report
from app.schemas.net_debt import NetDebtReport

router = APIRouter(tags=["Net Debt"])


@router.get("/deals/{deal_id}/net-debt", response_model=NetDebtReport)
def get_net_debt(deal_id: str) -> NetDebtReport:
    try:
        return load_net_debt_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
