"""Databook export API."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.v1.deps import get_current_user, require_deal_owner
from app.pipeline.databook.generator import DatabookError, generate
from app.security.access_log import log_document_access

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Databook"])


@router.post("/deals/{deal_id}/databook/export")
def export_databook(
    deal: dict = Depends(require_deal_owner), current_user: dict = Depends(get_current_user)
) -> Response:
    deal_id = deal["deal_id"]
    try:
        content = generate(deal_id)
    except DatabookError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Not a "missing prerequisite" — something genuinely broke while assembling the
        # workbook (e.g. malformed report JSON, openpyxl write error). Log with deal
        # context before the global handler's generic 500 takes over.
        logger.exception("Databook export failed unexpectedly for deal %s", deal_id)
        raise HTTPException(
            status_code=500, detail=f"Databook export failed: {exc}"
        ) from exc

    log_document_access(
        user_id=current_user["id"], deal_id=deal_id, action="export_databook",
    )

    safe_name = deal["deal_name"].replace(" ", "_")
    filename = f"{safe_name}_FDD_Databook.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
