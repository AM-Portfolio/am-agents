"""Prometheus ObservabilityPort unit tests (no cluster required for parse helpers)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from am_platform_adapters.providers.prometheus.observability import (
    PrometheusObservability,
    _extract_scalar,
    _parse_pass_when,
    _render,
)


def test_render_and_escape() -> None:
    q = _render('ns="{{namespace}}"', {"namespace": 'infra"x'})
    assert 'infra\\"x' in q


def test_pass_when() -> None:
    assert _parse_pass_when("value > 0", 2.0, None) is True
    assert _parse_pass_when("value > 0", 0.0, None) is False
    assert _parse_pass_when("value == 0", 0.0, None) is True


def test_extract_scalar_empty() -> None:
    assert _extract_scalar({"data": {"result": []}}) == 0.0


def test_extract_scalar_sum() -> None:
    body = {
        "data": {
            "result": [
                {"value": [1, "1"]},
                {"value": [1, "2.5"]},
            ]
        }
    }
    assert _extract_scalar(body) == 3.5


def test_unknown_query_ref_fails_closed_with_reason() -> None:
    o = PrometheusObservability("http://localhost:9090/prometheus")
    out = o.query(query_ref="does.not.exist", variables={"namespace": "infra"})
    assert out["pass"] is False
    assert out["source"] == "prometheus"
    assert out["error"]
    assert "unknown query_ref" in out["reason"]


def test_zero_value_fails_with_explicit_reason() -> None:
    o = PrometheusObservability("http://localhost:9090/prometheus")
    fake_body = {"status": "success", "data": {"result": [{"value": [1, "0"]}]}}
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"status":"success","data":{"result":[{"value":[1,"0"]}]}}'
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch(
        "am_platform_adapters.providers.prometheus.observability.urllib.request.urlopen",
        return_value=mock_resp,
    ):
        # Re-encode properly
        import json

        mock_resp.read.return_value = json.dumps(fake_body).encode("utf-8")
        out = o.query(
            query_ref="k8s.endpoints.ready",
            variables={"namespace": "infra", "service": "redis"},
        )
    assert out["pass"] is False
    assert out["source"] == "prometheus"
    assert out["value"] == 0.0
    assert "does not satisfy" in out["reason"]
    assert "prometheus" in out["reason"].lower()


def test_unreachable_prometheus_fails_closed_with_reason() -> None:
    o = PrometheusObservability("http://localhost:9/prometheus")
    with patch(
        "am_platform_adapters.providers.prometheus.observability.urllib.request.urlopen",
        side_effect=OSError("connection refused"),
    ):
        out = o.query(
            query_ref="k8s.endpoints.ready",
            variables={"namespace": "infra", "service": "redis"},
        )
    assert out["pass"] is False
    assert out["source"] == "prometheus"
    assert out["error"]
    assert "unreachable" in out["reason"].lower() or "unreachable" in (out["error"] or "").lower()


def test_redis_service_alive_query_exists() -> None:
    o = PrometheusObservability("http://localhost:9090/prometheus")
    assert "redis.service.alive" in o._queries


def test_live_redis_ready_when_prometheus_up() -> None:
    """Integration smoke — skip if Prometheus port-forward is down."""
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen("http://localhost:9090/prometheus/-/ready", timeout=2)
    except (urllib.error.URLError, TimeoutError, OSError):
        return

    o = PrometheusObservability("http://localhost:9090/prometheus")
    ready = o.query(
        query_ref="k8s.endpoints.ready",
        variables={"namespace": "infra", "service": "redis", "deployment": "redis"},
    )
    alive = o.query(
        query_ref="redis.service.alive",
        variables={"namespace": "infra", "service": "redis"},
    )
    assert ready.get("pass") is True, ready
    assert ready.get("reason"), ready
    assert alive.get("pass") is True, alive
    assert alive.get("source") == "prometheus"
    down = o.query(
        query_ref="k8s.endpoints.ready",
        variables={"namespace": "infra", "service": "nosuch-service-xyz"},
    )
    assert down.get("pass") is False, down
    assert down.get("reason"), down
