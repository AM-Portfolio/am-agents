"""Plane A observability: Prometheus /metrics + optional OTLP traces.

All Prometheus series carry an ``application`` label for Grafana discovery.
Sampling rate comes from env ``TRACING_SAMPLING_PROBABILITY`` (Vault-injected).
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, Request, Response

logger = logging.getLogger(__name__)

_EXCLUDED_PATHS = {"/metrics", "/health", "/router/health", "/ready", "/health/live", "/health/ready", "/api/v1/health"}
_instrumented_dependencies: set[str] = set()


def setup_plane_a(app: FastAPI, *, application: str) -> None:
    """Expose /metrics with application= label and optionally enable OTEL."""
    _setup_metrics(app, application)
    _setup_tracing(app, application)


def _setup_metrics(app: FastAPI, application: str) -> None:
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
    except ImportError:
        logger.warning("prometheus_client missing — /metrics not enabled")
        return

    up = Gauge("am_process_up", "1 if the process is up", ["application"])
    up.labels(application=application).set(1)

    requests_total = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["application", "method", "handler", "status"],
    )
    request_duration = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["application", "method", "handler"],
    )

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        path = request.url.path
        if path in _EXCLUDED_PATHS:
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        handler = path if len(path) < 120 else path[:117] + "..."
        requests_total.labels(application, request.method, handler, str(response.status_code)).inc()
        request_duration.labels(application, request.method, handler).observe(elapsed)
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    logger.info("Prometheus /metrics enabled application=%s", application)


def _setup_tracing(app: FastAPI, service_name: str) -> None:
    endpoint = (os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip()
    if not endpoint:
        logger.info("OTEL endpoint unset — tracing disabled")
        return

    try:
        sample = float(os.getenv("TRACING_SAMPLING_PROBABILITY", "1.0"))
    except ValueError:
        sample = 1.0
    sample = max(0.0, min(1.0, sample))

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    except ImportError:
        logger.warning("opentelemetry deps missing — tracing not enabled")
        return

    resource = Resource.create(
        {
            "service.name": service_name,
            "application": service_name,
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(sample)),
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="metrics,health,ready,router/health,health/live,health/ready,api/v1/health",
    )
    _instrument_dependencies()
    logger.info(
        "OTEL tracing enabled service=%s sample=%s endpoint=%s",
        service_name,
        sample,
        endpoint,
    )


def _instrument_dependencies() -> tuple[str, ...]:
    """Continue incoming trace context through tool and backend I/O."""
    instrumentors = (
        (
            "httpx",
            "opentelemetry.instrumentation.httpx",
            "HTTPXClientInstrumentor",
        ),
        (
            "asyncpg",
            "opentelemetry.instrumentation.asyncpg",
            "AsyncPGInstrumentor",
        ),
        (
            "pymongo",
            "opentelemetry.instrumentation.pymongo",
            "PymongoInstrumentor",
        ),
        (
            "redis",
            "opentelemetry.instrumentation.redis",
            "RedisInstrumentor",
        ),
    )
    for name, module_name, class_name in instrumentors:
        if name in _instrumented_dependencies:
            continue
        try:
            module = __import__(module_name, fromlist=[class_name])
            getattr(module, class_name)().instrument()
        except ImportError:
            logger.info("%s OTEL instrumentation unavailable", name)
            continue
        except Exception:  # noqa: BLE001 — tracing must not stop tool execution
            logger.exception("failed to enable %s OTEL instrumentation", name)
            continue
        _instrumented_dependencies.add(name)
        logger.info("%s OTEL instrumentation enabled", name)
    return tuple(sorted(_instrumented_dependencies))
