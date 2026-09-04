"""Structured debug logging for the finance agent (trace/user/session on every line)."""
from __future__ import annotations

import logging
from logging import LogRecord
from typing import Any

from shared.context.request_context import session_id_var, trace_id_var, user_id_var

# Keys that cannot be passed via logging `extra` (reserved on LogRecord).
_RESERVED_LOG_KEYS = frozenset(vars(LogRecord("", 0, "", 0, "", (), None)).keys())


def _safe_extra_key(key: str) -> str:
    if key in _RESERVED_LOG_KEYS:
        return f"ctx_{key}"
    return key


def _base_fields(**fields: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "trace_id": trace_id_var.get() or "-",
        "userId": user_id_var.get() or "-",
        "sessionId": session_id_var.get() or "-",
    }
    for key, value in fields.items():
        safe_key = _safe_extra_key(key)
        if isinstance(value, str) and len(value) > 800:
            out[safe_key] = value[:797] + "..."
        else:
            out[safe_key] = value
    return out


def _emit(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    *,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    extra = _base_fields(**fields)
    extra["event"] = event
    logger.log(level, message, extra=extra, exc_info=exc_info)


def log_agent_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Info-level structured event (primary debug trail)."""
    parts = [f"{_safe_extra_key(k)}={fields[k]!r}" for k in sorted(fields)]
    message = f"{event}" + (f" | {' | '.join(parts)}" if parts else "")
    _emit(logger, logging.INFO, event, message, **fields)


def log_agent_warning(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Warning-level structured event."""
    parts = [f"{k}={fields[k]!r}" for k in sorted(fields)]
    message = f"{event}" + (f" | {' | '.join(parts)}" if parts else "")
    _emit(logger, logging.WARNING, event, message, **fields)


def log_agent_error(
    logger: logging.Logger,
    event: str,
    error: str | BaseException | None = None,
    *,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    """Error-level event with optional exception details."""
    if error is not None:
        fields["error"] = str(error)
    parts = [f"{k}={fields[k]!r}" for k in sorted(fields)]
    message = f"{event}" + (f" | {' | '.join(parts)}" if parts else "")
    _emit(logger, logging.ERROR, event, message, exc_info=exc_info, **fields)


def log_agent_debug(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Debug-level event (verbose; enable with LOG_LEVEL=DEBUG)."""
    parts = [f"{k}={fields[k]!r}" for k in sorted(fields)]
    message = f"{event}" + (f" | {' | '.join(parts)}" if parts else "")
    _emit(logger, logging.DEBUG, event, message, **fields)
