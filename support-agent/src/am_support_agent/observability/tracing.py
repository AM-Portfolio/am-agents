"""Optional OpenTelemetry setup with payload-safe support-agent spans."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, MutableMapping

from fastapi import FastAPI

from am_support_agent.contracts.schemas import TaskRequest, TaskResult

LOG = logging.getLogger(__name__)
_FALSE = {"0", "false", "no", "off"}
_provider: Any = None
_instrumented_dependencies: set[str] = set()


def tracing_enabled() -> bool:
    """Return whether tracing was requested by environment configuration."""
    if os.getenv("OTEL_SDK_DISABLED", "").strip().lower() in {"1", "true", "yes"}:
        return False
    if os.getenv("SUPPORT_AGENT_TRACING_ENABLED", "true").strip().lower() in _FALSE:
        return False
    return bool(_trace_endpoint())


def setup_tracing(app: FastAPI, *, service_name: str = "support-agent") -> bool:
    """Instrument FastAPI and configure an OTLP/HTTP exporter when available."""
    if not configure_tracing(service_name=service_name):
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        LOG.warning("FastAPI OpenTelemetry instrumentation unavailable")
        return False

    if not getattr(app.state, "support_agent_tracing_instrumented", False):
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="metrics,healthz,readyz",
        )
        app.state.support_agent_tracing_instrumented = True
    return True


def configure_tracing(*, service_name: str = "support-agent") -> bool:
    """Configure the shared tracer provider for gateways or workers."""
    global _provider
    if not tracing_enabled():
        LOG.info("support-agent tracing disabled")
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    except ImportError:
        LOG.warning("OpenTelemetry dependencies unavailable; tracing disabled")
        return False

    if _provider is None:
        sample = _sample_probability()
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.namespace": os.getenv(
                    "OTEL_SERVICE_NAMESPACE", "am-agents"
                ),
                "service.version": os.getenv("SUPPORT_AGENT_VERSION", "0.1.0"),
                "deployment.environment.name": os.getenv(
                    "DEPLOYMENT_ENVIRONMENT", "unknown"
                ),
                "application": service_name,
            }
        )
        _provider = TracerProvider(
            resource=resource,
            sampler=ParentBased(TraceIdRatioBased(sample)),
        )
        _provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=_trace_endpoint()))
        )
        trace.set_tracer_provider(_provider)

    instrument_dependencies()
    return True


def instrument_dependencies() -> tuple[str, ...]:
    """Auto-instrument outbound I/O so it remains under the current OTel span.

    Instrumentors are optional at import time: the gateway always has HTTPX,
    while psycopg is installed only in deployments using the Postgres store.
    """
    instrumentors = (
        (
            "httpx",
            "opentelemetry.instrumentation.httpx",
            "HTTPXClientInstrumentor",
        ),
        (
            "psycopg",
            "opentelemetry.instrumentation.psycopg",
            "PsycopgInstrumentor",
        ),
    )
    for name, module_name, class_name in instrumentors:
        if name in _instrumented_dependencies:
            continue
        try:
            module = __import__(module_name, fromlist=[class_name])
            instrumentor = getattr(module, class_name)()
            instrumentor.instrument()
        except ImportError:
            LOG.info("%s OpenTelemetry instrumentation unavailable", name)
            continue
        except Exception:  # noqa: BLE001 — tracing must not stop the service
            LOG.exception("failed to enable %s OpenTelemetry instrumentation", name)
            continue
        _instrumented_dependencies.add(name)
        LOG.info("%s OpenTelemetry instrumentation enabled", name)
    return tuple(sorted(_instrumented_dependencies))


@contextmanager
def task_span(request: TaskRequest) -> Iterator[Any]:
    """Create a safe task span; no payload, auth, URL, or idempotency values."""
    try:
        from opentelemetry import trace
    except ImportError:
        yield _NullSpan()
        return
    attributes = safe_task_attributes(request)
    with trace.get_tracer("am_support_agent").start_as_current_span(
        "support_agent.task",
        attributes=attributes,
    ) as span:
        yield span


@contextmanager
def specialist_span(request: TaskRequest) -> Iterator[Any]:
    """Create the outbound specialist span used for context propagation."""
    try:
        from opentelemetry import trace
    except ImportError:
        yield _NullSpan()
        return
    with trace.get_tracer("am_support_agent").start_as_current_span(
        "support_agent.specialist",
        attributes=safe_task_attributes(request),
    ) as span:
        yield span


def safe_task_attributes(request: TaskRequest) -> dict[str, str]:
    """Return the complete, deliberately allowlisted task span attributes."""
    return {
        "agent.id": "support-agent",
        "specialist.agent": request.agent_id,
        "operation": request.op.value,
        "capability": request.capability,
        "task.id": request.task_id,
        "correlation.id": request.correlation_id,
        "business.domain": request.business_domain.value,
        "automation.mode": (
            "human_needed" if request.requires_human else "automated"
        ),
    }


def finish_task_span(span: Any, result: TaskResult) -> None:
    span.set_attribute("task.status", result.status.value)
    if result.error is not None:
        span.set_attribute("error.type", result.error.code)


def inject_trace_headers(headers: MutableMapping[str, str]) -> None:
    """Inject W3C trace context into a specialist request."""
    try:
        from opentelemetry.propagate import inject
    except ImportError:
        return
    inject(headers)


def temporal_interceptors() -> list[Any]:
    """Use Temporal's deterministic tracing interceptor when installed."""
    if not tracing_enabled():
        return []
    try:
        from temporalio.contrib.opentelemetry import TracingInterceptor
    except ImportError:
        LOG.warning("Temporal OpenTelemetry interceptor unavailable")
        return []
    return [TracingInterceptor()]


def attributes_are_safe(attributes: Mapping[str, Any]) -> bool:
    """Test helper enforcing the span attribute allowlist."""
    return set(attributes).issubset(
        {
            "agent.id",
            "specialist.agent",
            "operation",
            "capability",
            "task.id",
            "correlation.id",
            "business.domain",
            "automation.mode",
        }
    )


def _trace_endpoint() -> str:
    traces_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    if traces_endpoint:
        return traces_endpoint
    base_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    return f"{base_endpoint.rstrip('/')}/v1/traces" if base_endpoint else ""


def _sample_probability() -> float:
    raw = os.getenv(
        "OTEL_TRACES_SAMPLER_ARG",
        os.getenv("TRACING_SAMPLING_PROBABILITY", "1.0"),
    )
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 1.0


class _NullSpan:
    def set_attribute(self, _name: str, _value: Any) -> None:
        return None
