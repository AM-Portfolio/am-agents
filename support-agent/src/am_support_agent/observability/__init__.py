"""Support-agent observability."""

from am_support_agent.observability.metrics import (
    Metrics,
    get_shared_metrics,
    set_shared_metrics,
)
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
    "get_shared_metrics",
    "set_shared_metrics",
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
