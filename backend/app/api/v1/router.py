from fastapi import APIRouter

from app.api.v1 import databook, documents, financial, gl, ingestion, qoe, redflags

router = APIRouter(prefix="/api/v1")
router.include_router(ingestion.router)
router.include_router(documents.router)
router.include_router(gl.router)
router.include_router(financial.router)
router.include_router(qoe.router)
router.include_router(redflags.router)
router.include_router(databook.router)
