"""GET /api/v1/deals/{deal_id}/net-debt — net debt bridge + instrument detail."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import require_deal_owner
from app.pipeline.net_debt_bridge.orchestrator import load_net_debt_report
from app.schemas.net_debt import NetDebtReport

router = APIRouter(tags=["Net Debt"])


@router.get("/deals/{deal_id}/net-debt", response_model=NetDebtReport)
def get_net_debt(deal_id: str, _owned_deal: dict = Depends(require_deal_owner)) -> NetDebtReport:
    try:
        return load_net_debt_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
