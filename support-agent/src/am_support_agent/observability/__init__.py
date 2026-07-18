"""Support-agent observability."""

from am_support_agent.observability.metrics import Metrics
from am_support_agent.observability.tracing import (
    configure_tracing,
    finish_task_span,
    inject_trace_headers,
    instrument_dependencies,
    safe_task_attributes,
    setup_tracing,
    specialist_span,
    task_span,
    temporal_interceptors,
    tracing_enabled,
)

__all__ = [
    "Metrics",
    "configure_tracing",
    "finish_task_span",
    "inject_trace_headers",
    "instrument_dependencies",
    "safe_task_attributes",
    "setup_tracing",
    "specialist_span",
    "task_span",
    "temporal_interceptors",
    "tracing_enabled",
]
