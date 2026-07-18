from __future__ import annotations

from fastapi import FastAPI

from am_support_agent.contracts.enums import A2AOp, SupportDomain, TaskStatus
from am_support_agent.contracts.schemas import (
    TaskError,
    TaskMetrics,
    TaskRequest,
    TaskResult,
)
from am_support_agent.observability import Metrics
from am_support_agent.observability.tracing import (
    attributes_are_safe,
    inject_trace_headers,
    safe_task_attributes,
    setup_tracing,
    tracing_enabled,
)


def _request(**updates) -> TaskRequest:
    values = {
        "task_id": "task-secret-shaped-id",
        "correlation_id": "corr-1",
        "agent_id": "tool-agent",
        "capability": "tools.execute",
        "op": A2AOp.EXECUTE,
        "business_domain": SupportDomain.TECHNICAL,
        "requires_human": False,
        "idempotency_key": "do-not-export",
        "payload": {"password": "never-export", "url": "https://secret.invalid"},
    }
    values.update(updates)
    return TaskRequest(**values)


def test_tracing_disabled_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("SUPPORT_AGENT_TRACING_ENABLED", "true")
    assert tracing_enabled() is False
    assert setup_tracing(FastAPI()) is False


def test_tracing_can_be_enabled_without_contacting_collector(monkeypatch):
    from opentelemetry.exporter.otlp.proto.http import trace_exporter
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    monkeypatch.setenv("SUPPORT_AGENT_TRACING_ENABLED", "true")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "http://127.0.0.1:4318/v1/traces",
    )
    monkeypatch.setattr(
        trace_exporter,
        "OTLPSpanExporter",
        lambda **_kwargs: InMemorySpanExporter(),
    )
    assert tracing_enabled() is True
    assert setup_tracing(FastAPI()) is True


def test_span_attributes_are_allowlisted_and_payload_safe():
    request = _request()
    attributes = safe_task_attributes(request)
    assert attributes_are_safe(attributes)
    serialized = repr(attributes)
    assert "never-export" not in serialized
    assert "do-not-export" not in serialized
    assert "secret.invalid" not in serialized
    assert attributes["business.domain"] == "technical"


def test_traceparent_is_propagated_to_outbound_calls():
    from opentelemetry.context import attach, detach
    from opentelemetry.trace import (
        NonRecordingSpan,
        SpanContext,
        TraceFlags,
        set_span_in_context,
    )

    span_context = SpanContext(
        trace_id=int("1234567890abcdef1234567890abcdef", 16),
        span_id=int("1234567890abcdef", 16),
        is_remote=False,
        trace_flags=TraceFlags.SAMPLED,
    )
    token = attach(set_span_in_context(NonRecordingSpan(span_context)))
    try:
        headers: dict[str, str] = {}
        inject_trace_headers(headers)
    finally:
        detach(token)

    assert headers["traceparent"] == (
        "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
    )


def test_prometheus_metrics_include_technical_and_business_series():
    metrics = Metrics()
    request = _request(requires_human=True)
    result = TaskResult(
        task_id=request.task_id,
        agent_id=request.agent_id,
        status=TaskStatus.TIMED_OUT,
        error=TaskError(code="timeout", message="private upstream detail"),
        metrics=TaskMetrics(latency_ms=250),
    )
    metrics.task_started(request)
    metrics.observe(request, result)
    metrics.idempotency_hit(request)
    metrics.set_run_store_health(True)
    metrics.observe_parity(SupportDomain.TECHNICAL, False)
    metrics.observe_episode(result="write")
    metrics.observe_feedback(result="write")
    metrics.observe_retrieval(result="hit")
    metrics.observe_learning(kind="evaluation")
    metrics.set_episode_store_health(True)
    metrics.set_feedback_store_health(True)

    rendered = metrics.render()
    assert "support_agent_adapter_latency_seconds_bucket" in rendered
    assert 'op="execute",agent="tool-agent"} 1' in rendered
    assert "support_agent_idempotency_hits_total" in rendered
    assert "support_agent_in_flight_tasks" in rendered
    assert 'support_agent_run_store_healthy{application="support-agent"} 1' in rendered
    assert "support_agent_memory_events_total" in rendered
    assert "support_agent_learning_events_total" in rendered
    assert "support_agent_episode_store_healthy" in rendered
    assert 'domain="technical"} 1' in rendered
    assert 'outcome="timed_out"' in rendered
    assert 'mode="human_needed"' in rendered
    assert "support_agent_hitl_total" in rendered
    assert 'domain="technical",result="fail"' in rendered
    assert "private upstream detail" not in rendered
    assert "task-secret-shaped-id" not in rendered
    assert "corr-1" not in rendered


def test_business_domain_rejects_unbounded_values():
    try:
        _request(business_domain="customer-free-text")
    except ValueError:
        pass
    else:
        raise AssertionError("business_domain accepted a non-allowlisted value")
