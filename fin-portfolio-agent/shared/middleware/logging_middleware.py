"""
Structured JSON request/response logging middleware.
Uses X-Request-Id when present; sets ContextVars for downstream code.
Langfuse turn trace id is established in the chat handler (P0).
"""
import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from shared.context.request_context import trace_id_var, request_id_var

logger = logging.getLogger("am.fin.agent")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = (
            request.headers.get("x-request-id")
            or request.headers.get("X-Request-Id")
            or str(uuid.uuid4())
        )
        # Provisional correlation id until chat handler sets Langfuse turn trace id
        provisional_trace = request_id if len(request_id) >= 8 else str(uuid.uuid4())
        span_id = str(uuid.uuid4())[:8]

        request_id_var.set(request_id)
        trace_id_var.set(provisional_trace)

        start = time.time()
        logger.info(
            "request_start",
            extra={
                "trace_id": provisional_trace,
                "request_id": request_id,
                "span_id": span_id,
                "method": request.method,
                "path": str(request.url.path),
            }
        )

        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 2)
        final_trace = trace_id_var.get() or provisional_trace

        logger.info(
            "request_end",
            extra={
                "trace_id": final_trace,
                "request_id": request_id,
                "span_id": span_id,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            }
        )
        if "X-Trace-Id" not in response.headers and "x-trace-id" not in response.headers:
            response.headers["X-Trace-Id"] = final_trace
        if "X-Request-Id" not in response.headers and "x-request-id" not in response.headers:
            response.headers["X-Request-Id"] = request_id
        return response
