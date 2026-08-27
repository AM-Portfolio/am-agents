"""
Structured JSON request/response logging middleware.
Generates trace_id and span_id per request, sets ContextVars,
and logs in structured JSON format. Follows global coding standards:
  - JSON format in production
  - trace_id + span_id on every request
"""
import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from shared.context.request_context import trace_id_var, auth_token_var

logger = logging.getLogger("am.fin.agent")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())[:8]

        # Set trace_id in ContextVar so all downstream code can access it
        trace_id_var.set(trace_id)

        # Propagate auth token
        auth_header = request.headers.get("Authorization", "")
        auth_token_var.set(auth_header)

        start = time.time()
        logger.info(
            "request_start",
            extra={
                "trace_id": trace_id,
                "span_id": span_id,
                "method": request.method,
                "path": str(request.url.path),
            }
        )

        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 2)

        logger.info(
            "request_end",
            extra={
                "trace_id": trace_id,
                "span_id": span_id,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            }
        )
        # Propagate trace_id header to Flutter
        response.headers["X-Trace-Id"] = trace_id
        return response
