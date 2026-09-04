"""Central logging configuration for fin-agent (JSON in prod, text locally)."""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from shared.context.request_context import session_id_var, trace_id_var, user_id_var

_CONFIGURED = False
_ROOT_LOGGER = "am.fin.agent"


class RequestContextFilter(logging.Filter):
    """Attach trace/user/session to every log record for formatters."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get() or "-"  # type: ignore[attr-defined]
        record.userId = user_id_var.get() or "-"  # type: ignore[attr-defined]
        record.sessionId = session_id_var.get() or "-"  # type: ignore[attr-defined]
        record.event = getattr(record, "event", "-")  # type: ignore[attr-defined]
        return True


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line — works with kubectl logs and Loki."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "-"),
            "userId": getattr(record, "userId", "-"),
            "sessionId": getattr(record, "sessionId", "-"),
        }
        event = getattr(record, "event", None)
        if event and event != "-":
            payload["event"] = event

        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "trace_id", "userId", "sessionId", "event",
            }:
                continue
            if key in payload:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextLogFormatter(logging.Formatter):
    """Human-readable single line for local dev."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | "
            "trace=%(trace_id)s user=%(userId)s session=%(sessionId)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def configure_logging(*, force: bool = False) -> None:
    """Idempotent logging bootstrap. Call once at process start."""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = (os.getenv("LOG_FORMAT") or "text").lower()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestContextFilter())
    if log_format == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(TextLogFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for name in ("am.fin.agent", "am.fin.portfolio.api", "shared", "am_fin_portfolio_analysis"):
        pkg_logger = logging.getLogger(name)
        pkg_logger.handlers.clear()
        pkg_logger.propagate = True
        pkg_logger.setLevel(level)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger(_ROOT_LOGGER).info(
        "logging configured format=%s level=%s",
        log_format,
        level_name,
        extra={"event": "logging_configured"},
    )


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the am.fin.agent namespace."""
    if not _CONFIGURED:
        configure_logging()
    if name.startswith("am.fin."):
        return logging.getLogger(name)
    return logging.getLogger(f"am.fin.agent.{name}")
