"""
Centralised logging setup for the FDD Engine backend.

Call configure_logging() once at application startup (from main.py).
After that all modules use logging.getLogger(__name__) as normal.

Log format is plain text by default.
Set LOG_JSON=true in .env to emit newline-delimited JSON, which is
compatible with cloud log aggregators (Datadog, Loki, CloudWatch, etc.).
"""

import json
import logging
import sys
from datetime import UTC, datetime

from app.config import settings


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record on a single line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Attach any extra fields passed via the `extra` kwarg
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


_PLAIN_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging() -> None:
    """
    Configure root logger once.
    Reads LOG_LEVEL and LOG_JSON from settings / environment.
    Safe to call multiple times — subsequent calls are no-ops.
    """
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_PLAIN_FORMAT))

    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # Reduce verbosity from noisy third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
