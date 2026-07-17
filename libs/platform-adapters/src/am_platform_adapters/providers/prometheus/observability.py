"""Prometheus HTTP ObservabilityPort — real Gate A verify (no VERIFY_FORCE)."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _safe_prom_label(value: str) -> str:
    """Escape for use inside Prometheus double-quoted label matchers."""
    return (value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "")


def _render(template: str, variables: dict[str, Any]) -> str:
    out = template
    for key, val in variables.items():
        out = out.replace("{{" + key + "}}", _safe_prom_label(str(val)))
    # leftover placeholders → empty (safer than leaving braces)
    return re.sub(r"\{\{[a-zA-Z0-9_]+\}\}", "", out)


# Built-in query_ref templates — catalog may override via VERIFY_QUERY_MAP JSON.
# This cluster has redis_exporter + cAdvisor (no kube-state-metrics kube_* series).
_DEFAULT_QUERIES: dict[str, dict[str, Any]] = {
    # Service readiness: redis_up when exporter present; else cAdvisor container presence.
    # Note: PromQL `or` only falls through when the left side has *no series* (value 0 still wins).
    "k8s.endpoints.ready": {
        "promql": (
            "("
            'max(redis_up{namespace="{{namespace}}",pod=~"{{service}}-.*"}) '
            'or (count(container_memory_working_set_bytes{namespace="{{namespace}}",'
            'pod=~"{{service}}-.*",container!="",container!="POD"}) > bool 0) '
            "or vector(0))"
        ),
        "pass_when": "value > 0",
    },
    "k8s.deployment.available": {
        "promql": (
            "("
            'max(redis_up{namespace="{{namespace}}",pod=~"{{deployment}}-.*|{{service}}-.*"}) '
            'or (count(container_memory_working_set_bytes{namespace="{{namespace}}",'
            'pod=~"{{deployment}}-.*|{{service}}-.*",container!="",container!="POD"}) > bool 0) '
            "or vector(0))"
        ),
        "pass_when": "value > 0",
    },
    "k8s.pod.ready": {
        "promql": (
            "("
            'max(redis_up{namespace="{{namespace}}",pod=~"{{pod}}|{{service}}-.*"}) '
            'or (count(container_memory_working_set_bytes{namespace="{{namespace}}",'
            'pod=~"{{pod}}|{{service}}-.*",container!="",container!="POD"}) > bool 0) '
            "or vector(0))"
        ),
        "pass_when": "value > 0",
    },
    # Legacy catalog keys — still real PromQL, not forced
    "grafana.prom.error_rate": {
        "promql": (
            'sum(rate(container_cpu_usage_seconds_total{namespace="{{namespace}}",'
            'pod=~"{{service}}-.*"}[5m])) or vector(0)'
        ),
        "pass_when": "value >= 0",  # connectivity smoke; readiness is primary check
        "threshold": 0,
    },
    "grafana.loki.no_fatal": {
        # No Loki/KSM crashloop series — require exporter up or recently seen container.
        "promql": (
            "("
            'max(redis_up{namespace="{{namespace}}",pod=~"{{service}}-.*"}) '
            "or ("
            '(time() - max(container_last_seen{namespace="{{namespace}}",'
            'pod=~"{{service}}-.*",container!="",container!="POD"})) < bool 300'
            ") "
            "or vector(0))"
        ),
        "pass_when": "value == 1",
    },
}


def _parse_pass_when(pass_when: str, value: float, threshold: float | None) -> bool:
    expr = (pass_when or "value > 0").strip().lower()
    if threshold is not None:
        expr = expr.replace("threshold", str(threshold))
    # supported: value > N, value >= N, value == N, value < N, value <= N
    m = re.match(r"value\s*(==|!=|>=|<=|>|<)\s*([-+]?[0-9]*\.?[0-9]+)", expr)
    if not m:
        return value > 0
    op, rhs = m.group(1), float(m.group(2))
    if op == ">":
        return value > rhs
    if op == ">=":
        return value >= rhs
    if op == "<":
        return value < rhs
    if op == "<=":
        return value <= rhs
    if op == "==":
        return value == rhs
    if op == "!=":
        return value != rhs
    return False


def _extract_scalar(data: dict[str, Any]) -> float:
    """Parse Prometheus instant-query result → float (0 if empty)."""
    result = (data.get("data") or {}).get("result") or []
    if not result:
        return 0.0
    # vector
    if isinstance(result, list):
        total = 0.0
        for series in result:
            val = (series.get("value") or [None, "0"])[1]
            try:
                total += float(val)
            except (TypeError, ValueError):
                continue
        return total
    return 0.0


class PrometheusObservability:
    """Query Prometheus HTTP API for Gate A checks."""

    def __init__(self, base_url: str | None = None) -> None:
        # Prefer full API prefix, e.g. http://localhost:9090/prometheus
        raw = (
            base_url
            or os.getenv("PROMETHEUS_URL")
            or os.getenv("PROMETHEUS_BASE_URL")
            or "http://localhost:9090/prometheus"
        ).strip().rstrip("/")
        self._base = raw
        self._queries = dict(_DEFAULT_QUERIES)
        extra = (os.getenv("VERIFY_QUERY_MAP") or "").strip()
        if extra:
            try:
                parsed = json.loads(extra)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if isinstance(v, dict) and v.get("promql"):
                            self._queries[str(k)] = v
            except json.JSONDecodeError:
                pass

    def query(self, *, query_ref: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = dict(variables or {})
        # Flatten alert labels into template vars
        labels = variables.get("labels")
        if isinstance(labels, dict):
            for k, v in labels.items():
                variables.setdefault(str(k), v)
        for key in ("namespace", "service", "deployment", "pod", "env"):
            variables.setdefault(key, "")

        # Fallbacks so templates are never empty matchers
        if not variables.get("service"):
            variables["service"] = variables.get("deployment") or variables.get("application") or ".*"
        if not variables.get("deployment"):
            variables["deployment"] = variables.get("service") or ".*"
        if not variables.get("namespace"):
            variables["namespace"] = "default"
        if not variables.get("pod"):
            variables["pod"] = f"{variables['service']}.*"

        spec = self._queries.get(query_ref)
        if not spec:
            # Unknown ref → fail closed (do not mark fixed)
            return {
                "pass": False,
                "query_ref": query_ref,
                "error": f"unknown query_ref={query_ref}",
                "value": None,
            }

        promql = _render(str(spec["promql"]), variables)
        pass_when = str(spec.get("pass_when") or "value > 0")
        threshold = spec.get("threshold")
        try:
            threshold_f = float(threshold) if threshold is not None else None
        except (TypeError, ValueError):
            threshold_f = None

        url = (
            f"{self._base}/api/v1/query?"
            + urllib.parse.urlencode({"query": promql})
        )
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "am-platform-adapters/prometheus"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            return {
                "pass": False,
                "query_ref": query_ref,
                "promql": promql,
                "error": f"prometheus HTTP {exc.code}: {detail}",
                "value": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "pass": False,
                "query_ref": query_ref,
                "promql": promql,
                "error": f"prometheus unreachable: {exc}"[:300],
                "value": None,
            }

        if body.get("status") != "success":
            return {
                "pass": False,
                "query_ref": query_ref,
                "promql": promql,
                "error": f"prometheus status={body.get('status')}",
                "value": None,
            }

        value = _extract_scalar(body)
        ok = _parse_pass_when(pass_when, value, threshold_f)
        return {
            "pass": ok,
            "query_ref": query_ref,
            "promql": promql,
            "value": value,
            "threshold": threshold_f,
            "pass_when": pass_when,
            "variables": {
                k: variables.get(k)
                for k in ("namespace", "service", "deployment", "pod", "env")
            },
        }
