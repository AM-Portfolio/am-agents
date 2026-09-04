"""
Structured request logging middleware.
Generates trace_id per request, sets ContextVars, logs start/end as JSON events.
"""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from shared.context.jwt_context import resolve_request_user_id
from shared.context.request_context import auth_token_var, session_id_var, trace_id_var, user_id_var
from shared.observability.agent_log import log_agent_error, log_agent_event
from shared.observability.log_events import AgentLogEvent
from shared.observability.logging_setup import get_logger

logger = get_logger("http")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
        span_id = str(uuid.uuid4())[:8]
        trace_id_var.set(trace_id)

        auth_header = request.headers.get("Authorization", "")
        auth_token_var.set(auth_header)

        user_id, _jwt_sub = resolve_request_user_id(
            body_user_id=user_id_var.get() if user_id_var.get() not in {"", "-", "anonymous"} else None,
            header_user_id=request.headers.get("x-user-id"),
            auth_header=auth_header,
        )
        session_id = request.headers.get("x-session-id") or session_id_var.get() or ""
        user_id_var.set(user_id)
        if session_id:
            session_id_var.set(session_id)

        start = time.time()
        log_agent_event(
            logger,
            AgentLogEvent.REQUEST_START,
            span_id=span_id,
            method=request.method,
            path=str(request.url.path),
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            log_agent_error(
                logger,
                AgentLogEvent.REQUEST_ERROR,
                error=exc,
                exc_info=True,
                span_id=span_id,
                method=request.method,
                path=str(request.url.path),
            )
            raise

        duration_ms = round((time.time() - start) * 1000, 2)
        log_agent_event(
            logger,
            AgentLogEvent.REQUEST_END,
            span_id=span_id,
            status_code=response.status_code,
            duration_ms=duration_ms,
            path=str(request.url.path),
        )
        response.headers["X-Trace-Id"] = trace_id
        return response
