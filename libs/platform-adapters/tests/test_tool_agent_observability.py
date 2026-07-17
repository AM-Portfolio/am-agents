"""Tool-agent ObservabilityPort unit tests (no cluster required for helpers)."""

from __future__ import annotations

from am_platform_adapters.providers.tool_agent.observability import _is_redis, _service_name


def test_is_redis_from_service() -> None:
    assert _is_redis({"service": "redis", "namespace": "infra"}) is True
    assert _is_redis({"service": "payment-api", "namespace": "apps"}) is False


def test_service_name_from_labels() -> None:
    assert _service_name({"labels": {"service": "redis"}}) == "redis"
