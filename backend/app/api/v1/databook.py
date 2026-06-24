"""Databook export API."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.pipeline.databook.generator import DatabookError, generate
from app.storage import deal_store

router = APIRouter(tags=["Databook"])


@router.post("/deals/{deal_id}/databook/export")
def export_databook(deal_id: str) -> Response:
    deal = deal_store.get_deal(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")

    try:
        content = generate(deal_id)
    except DatabookError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    safe_name = deal["deal_name"].replace(" ", "_")
    filename = f"{safe_name}_FDD_Databook.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
