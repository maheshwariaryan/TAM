from fastapi import APIRouter

from app.api.v1 import (
    auth,
    contracts,
    databook,
    dcf,
    documents,
    financial,
    gl,
    ingestion,
    narrative,
    net_debt,
    notes,
    nwc,
    qoe,
    redflags,
    tieouts,
)

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(ingestion.router)
router.include_router(documents.router)
router.include_router(gl.router)
router.include_router(financial.router)
router.include_router(qoe.router)
router.include_router(redflags.router)
router.include_router(nwc.router)
router.include_router(net_debt.router)
router.include_router(dcf.router)
router.include_router(contracts.router)
router.include_router(narrative.router)
router.include_router(notes.router)
router.include_router(tieouts.router)
router.include_router(databook.router)
