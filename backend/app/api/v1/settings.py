"""
Deal-scoped diligence settings API.

GET   /api/v1/deals/{deal_id}/settings   Current settings (today's UI defaults if none saved yet)
PATCH /api/v1/deals/{deal_id}/settings   Partial update, merged onto current settings
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.api.v1.deps import require_deal_owner
from app.schemas.settings import DealSettings, DealSettingsUpdate, get_deal_settings
from app.storage import deal_store

router = APIRouter(tags=["Settings"])


@router.get("/deals/{deal_id}/settings", response_model=DealSettings)
def get_settings(deal: dict = Depends(require_deal_owner)) -> DealSettings:
    return get_deal_settings(deal)


@router.patch("/deals/{deal_id}/settings", response_model=DealSettings)
def update_settings(
    body: DealSettingsUpdate, deal: dict = Depends(require_deal_owner)
) -> DealSettings:
    current = get_deal_settings(deal)
    try:
        merged = DealSettings.model_validate(
            {**current.model_dump(), **body.model_dump(exclude_none=True)}
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    deal_store.update_deal(deal["deal_id"], {"settings": merged.model_dump(mode="json")})
    return merged
