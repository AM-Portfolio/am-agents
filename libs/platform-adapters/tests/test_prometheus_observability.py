"""Prometheus ObservabilityPort unit tests (no cluster required for parse helpers)."""

from __future__ import annotations

from am_platform_adapters.providers.prometheus.observability import (
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


def test_live_redis_ready_when_prometheus_up() -> None:
    """Integration smoke — skip if Prometheus port-forward is down."""
    import urllib.error
    import urllib.request

    from am_platform_adapters.providers.prometheus import PrometheusObservability

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
        query_ref="grafana.loki.no_fatal",
        variables={"namespace": "infra", "service": "redis"},
    )
    assert ready.get("pass") is True, ready
    assert alive.get("pass") is True, alive
    down = o.query(
        query_ref="k8s.endpoints.ready",
        variables={"namespace": "infra", "service": "nosuch-service-xyz"},
    )
    assert down.get("pass") is False, down
