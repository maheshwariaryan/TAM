"""
FDD Engine — FastAPI application factory.
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.config import settings
from app.logging_config import configure_logging

configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="FDD Engine API",
    description=(
        "Automated Financial Due Diligence engine for M&A Transaction Advisory Services. "
        "Ingests GL exports, trial balances, and contracts; produces QoE analysis, "
        "NWC trends, commercial health metrics, and red flag reports."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next) -> Response:
    """
    Log every HTTP request with method, path, status code, duration, and a
    unique request ID.  The request ID is echoed back in the response header
    so that frontend errors can be correlated with backend log entries.

    Request/response bodies are intentionally not logged — uploads and
    financial payloads may contain sensitive data.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start = time.perf_counter()

    response = await call_next(request)

    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "%s %s → %d  (%.1fms) req_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )

    return response


app.include_router(v1_router)


@app.get("/health", tags=["System"])
def health_check() -> dict:
    return {
        "status": "ok",
        "version": "0.1.0",
        "mock_llm": settings.use_mock_llm,
    }
