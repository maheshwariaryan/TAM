"""
FDD Engine — FastAPI application factory.
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
async def hsts_middleware(request: Request, call_next) -> Response:
    """
    Strict-Transport-Security tells browsers to only ever contact this host
    over HTTPS for the given max-age, once they've seen it over HTTPS at least
    once. This app does not terminate TLS itself (see README.md) — a reverse
    proxy (nginx/Caddy) or load balancer must sit in front of it in any
    non-localhost deployment. Sending the header here is harmless over plain
    HTTP (browsers ignore HSTS on non-HTTPS responses) and means the proxy
    doesn't have to be separately configured to add it.
    """
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


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
    request.state.request_id = request_id
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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Last-resort safety net: no request should ever return a bare, contentless
    500. Every uncaught exception is logged here with a full traceback through
    the app's own logger (so it respects LOG_JSON/logging_config.py, unlike
    uvicorn's internal error logger), and the client gets a structured error
    body with enough detail to debug without switching to the terminal — this
    is a local, single-operator tool, so there is no reason to hide detail.
    """
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    logger.exception(
        "Unhandled exception on %s %s (req_id=%s): %s",
        request.method, request.url.path, request_id, exc,
        extra={
            "event": "unhandled_exception", "request_id": request_id,
            "method": request.method, "path": request.url.path,
            "exception_type": type(exc).__name__,
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "detail": str(exc),
            "request_id": request_id,
            "endpoint": f"{request.method} {request.url.path}",
        },
        headers={"X-Request-ID": request_id},
    )


@app.get("/health", tags=["System"])
def health_check() -> dict:
    return {
        "status": "ok",
        "version": "0.1.0",
        "mock_llm": settings.use_mock_llm,
    }
