from __future__ import annotations

import pytest

from app.observability.sanitize import redact_value, sanitize_payload, truncate_for_trace


def test_redact_secret_keys():
    payload = {"password": "secret123", "query": "SELECT 1"}
    redacted = redact_value("", payload)
    assert redacted["password"] == "***"
    assert redacted["query"] == "SELECT 1"


def test_redact_url_credentials():
    url = "postgresql://user:pass@host:5432/db"
    assert "pass" not in redact_value("url", url)


def test_truncate_for_trace():
    long_text = "x" * 100
    result = truncate_for_trace(long_text, max_chars=20)
    assert isinstance(result, str)
    assert result.endswith("...(truncated)")


def test_sanitize_payload_nested():
    data = {"token": "abc", "rows": [{"id": 1}]}
    out = sanitize_payload(data, max_chars=500)
    assert out["token"] == "***"


@pytest.mark.asyncio
async def test_tracer_disabled_no_enqueue():
    import importlib

    tracer_module = importlib.import_module("app.observability.tracer")
    prev = tracer_module.tracer.enabled
    tracer_module.tracer.enabled = False
    try:
        await tracer_module.tracer.span("trace-1", "test", input={"a": 1})
        assert tracer_module._trace_queue is None
    finally:
        tracer_module.tracer.enabled = prev
