"""Tool-agent ObservabilityPort unit tests (no cluster required for helpers)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from am_platform_adapters.providers.tool_agent.observability import (
    PreferToolAgentObservability,
    ToolAgentObservability,
    _is_redis,
    _service_name,
    tool_agent_owns_query,
)


def test_is_redis_from_service() -> None:
    assert _is_redis({"service": "redis", "namespace": "infra"}) is True
    assert _is_redis({"service": "payment-api", "namespace": "apps"}) is False


def test_service_name_from_labels() -> None:
    assert _service_name({"labels": {"service": "redis"}}) == "redis"


def test_tool_agent_owns_only_service_alive_redis() -> None:
    vars_redis = {"service": "redis", "namespace": "infra"}
    assert tool_agent_owns_query(query_ref="redis.service.alive", variables=vars_redis) is True
    assert tool_agent_owns_query(query_ref="verify.service.alive", variables=vars_redis) is True
    # Endpoint readiness must NOT go to tool-agent redis.info
    assert tool_agent_owns_query(query_ref="k8s.endpoints.ready", variables=vars_redis) is False
    assert tool_agent_owns_query(query_ref="grafana.loki.no_fatal", variables=vars_redis) is False
    assert tool_agent_owns_query(
        query_ref="redis.service.alive",
        variables={"service": "payment-api"},
    ) is False


def test_prefer_routes_endpoints_to_prometheus_not_tool_agent() -> None:
    primary = MagicMock()
    fallback = MagicMock()
    fallback.query.return_value = {
        "pass": True,
        "source": "prometheus",
        "reason": "ok",
        "query_ref": "k8s.endpoints.ready",
    }
    prefer = PreferToolAgentObservability(primary, fallback)
    vars_redis = {"service": "redis", "namespace": "infra"}

    out = prefer.query(query_ref="k8s.endpoints.ready", variables=vars_redis)
    assert out["source"] == "prometheus"
    primary.query.assert_not_called()
    fallback.query.assert_called_once()

    primary.reset_mock()
    fallback.reset_mock()
    primary.query.return_value = {
        "pass": True,
        "source": "tool-agent:redis.info",
        "reason": "redis up",
        "query_ref": "redis.service.alive",
    }
    out2 = prefer.query(query_ref="redis.service.alive", variables=vars_redis)
    assert out2["source"] == "tool-agent:redis.info"
    primary.query.assert_called_once()
    fallback.query.assert_not_called()


def test_tool_agent_rejects_endpoints_ready_for_redis() -> None:
    o = ToolAgentObservability("http://localhost:8141")
    out = o.query(
        query_ref="k8s.endpoints.ready",
        variables={"service": "redis", "namespace": "infra"},
    )
    assert out["pass"] is False
    assert "redis.info" in (out.get("reason") or out.get("error") or "")
    assert out["source"] == "tool-agent"


def test_tool_agent_rejects_no_fatal_via_redis_info() -> None:
    o = ToolAgentObservability("http://localhost:8141")
    out = o.query(
        query_ref="grafana.loki.no_fatal",
        variables={"service": "redis", "namespace": "infra"},
    )
    assert out["pass"] is False
    assert "log" in (out.get("reason") or "").lower() or "fatal" in (out.get("reason") or "").lower()


def test_tool_agent_redis_info_pass_includes_reason() -> None:
    o = ToolAgentObservability("http://localhost:8141")
    with patch.object(
        o,
        "_post",
        return_value={
            "request_id": "req-1",
            "data": {"info": {"redis_version": "7.2.0", "uptime_in_seconds": 100}},
        },
    ):
        out = o.query(
            query_ref="redis.service.alive",
            variables={"service": "redis", "namespace": "infra"},
        )
    assert out["pass"] is True
    assert out["source"] == "tool-agent:redis.info"
    assert out["request_id"] == "req-1"
    assert "redis_version=7.2.0" in out["reason"]
    assert out["redis_version"] == "7.2.0"


def test_tool_agent_error_includes_failure_reason() -> None:
    o = ToolAgentObservability("http://localhost:8141")
    with patch.object(o, "_post", side_effect=OSError("boom")):
        out = o.query(
            query_ref="redis.service.alive",
            variables={"service": "redis", "namespace": "infra"},
        )
    assert out["pass"] is False
    assert out["error"]
    assert "failed" in out["reason"].lower() or "unreachable" in out["reason"].lower()
