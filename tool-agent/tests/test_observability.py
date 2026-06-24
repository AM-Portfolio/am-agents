import importlib

import pytest

from app.observability.sanitize import sanitize_payload


def test_sanitize_payload_truncates_long_strings():
    result = sanitize_payload("x" * 100, max_chars=20)
    assert len(result) == 21
    assert result.endswith("…")


@pytest.mark.asyncio
async def test_tracer_disabled_no_enqueue():
    tracer_module = importlib.import_module("app.observability.tracer")
    prev = tracer_module.tracer.enabled
    tracer_module.tracer.enabled = False
    try:
        await tracer_module.tracer.span("trace-1", "test", input={"a": 1})
        assert tracer_module._trace_queue is None
    finally:
        tracer_module.tracer.enabled = prev
