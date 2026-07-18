"""Observability via tool-agent (redis / grafana) when the query is in its domain."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

# Query refs tool-agent redis.info can semantically answer (process reachability / INFO).
_SERVICE_ALIVE_REFS = frozenset(
    {
        "redis.service.alive",
        "verify.service.alive",
        "service.alive",
    }
)


def _service_name(variables: dict[str, Any]) -> str:
    labels = variables.get("labels") if isinstance(variables.get("labels"), dict) else {}
    return str(
        variables.get("service")
        or variables.get("deployment")
        or (labels or {}).get("service")
        or (labels or {}).get("deployment")
        or ""
    ).strip().lower()


def _is_redis(variables: dict[str, Any]) -> bool:
    svc = _service_name(variables)
    alertname = str(variables.get("alertname") or "").lower()
    blob = f"{svc} {alertname} {variables.get('namespace','')}"
    return "redis" in svc or "redis" in blob


def _is_service_alive_ref(query_ref: str) -> bool:
    ref = (query_ref or "").strip().lower()
    if ref in _SERVICE_ALIVE_REFS:
        return True
    return ref.endswith(".service.alive") or ref.endswith("service.alive")


def tool_agent_owns_query(*, query_ref: str, variables: dict[str, Any] | None = None) -> bool:
    """True only when tool-agent can semantically answer this check (not endpoint readiness)."""
    variables = dict(variables or {})
    return _is_redis(variables) and _is_service_alive_ref(query_ref)


class ToolAgentObservability:
    """
    Gate A verify through tool-agent HTTP.

    - redis.service.alive (redis alerts) → redis.info (process-up / INFO)
    - k8s.endpoints.ready / log checks → NOT handled here (fail closed or Prefer* → Prometheus)
    Fail closed on errors / unknown refs.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base = (
            base_url
            or os.getenv("TOOL_AGENT_URL")
            or os.getenv("TOOL_AGENT_BASE_URL")
            or "http://localhost:8141"
        ).rstrip("/")
        self._prom_uid = (os.getenv("TOOL_AGENT_PROM_DATASOURCE_UID") or "").strip()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base}{path}",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Agent-Caller": os.getenv("TOOL_AGENT_CALLER", "platform-worker"),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _redis_info(self, *, query_ref: str, variables: dict[str, Any]) -> dict[str, Any]:
        source = "tool-agent:redis.info"
        try:
            out = self._post(
                "/api/v1/tools/execute",
                {
                    "intent": {
                        "backend": "redis",
                        "operation": "info",
                        "params": {},
                        "read_only": True,
                        "confidence": 1.0,
                        "rationale": f"Gate A verify {query_ref}",
                    },
                    "include_summary": False,
                    "read_only": True,
                },
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            err = f"tool-agent HTTP {exc.code}: {detail}"
            return {
                "pass": False,
                "query_ref": query_ref,
                "source": source,
                "error": err,
                "reason": f"Redis service-alive check failed via redis.info: {err}",
            }
        except Exception as exc:  # noqa: BLE001
            err = f"tool-agent unreachable: {exc}"[:300]
            return {
                "pass": False,
                "query_ref": query_ref,
                "source": source,
                "error": err,
                "reason": f"Redis service-alive check failed: {err}",
            }

        info = ((out.get("data") or {}) if isinstance(out, dict) else {}).get("info") or {}
        if not isinstance(info, dict):
            info = {}
        version = info.get("redis_version")
        uptime = info.get("uptime_in_seconds")
        ok = bool(version)
        if ok:
            reason = (
                f"Redis reachable via tool-agent redis.info "
                f"(redis_version={version}, uptime_in_seconds={uptime})"
            )
        else:
            reason = (
                "Redis service-alive failed: tool-agent redis.info returned no redis_version "
                "(process not confirmed up)"
            )
        return {
            "pass": ok,
            "query_ref": query_ref,
            "source": source,
            "value": 1.0 if ok else 0.0,
            "pass_when": "value == 1",
            "redis_version": version,
            "uptime_in_seconds": uptime,
            "request_id": out.get("request_id") if isinstance(out, dict) else None,
            "reason": reason,
            "variables": {
                k: variables.get(k) for k in ("namespace", "service", "deployment", "env")
            },
        }

    def query(self, *, query_ref: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = dict(variables or {})
        labels = variables.get("labels")
        if isinstance(labels, dict):
            for k, v in labels.items():
                variables.setdefault(str(k), v)

        # Only service-alive refs for redis → redis.info (not endpoint readiness / logs)
        if tool_agent_owns_query(query_ref=query_ref, variables=variables):
            return self._redis_info(query_ref=query_ref, variables=variables)

        ref_l = (query_ref or "").lower()
        if "endpoints" in ref_l or query_ref in {
            "k8s.endpoints.ready",
            "k8s.deployment.available",
            "k8s.pod.ready",
        }:
            err = (
                f"tool-agent cannot prove {query_ref} via redis.info; "
                "use OBSERVE_PROVIDER=prometheus (redis_up/cAdvisor)"
            )
            return {
                "pass": False,
                "query_ref": query_ref,
                "source": "tool-agent",
                "error": err,
                "reason": err,
            }

        if "no_fatal" in ref_l or "loki" in ref_l:
            err = (
                f"tool-agent cannot check logs for {query_ref}; "
                "redis.info is not a log/fatal check — fail closed"
            )
            return {
                "pass": False,
                "query_ref": query_ref,
                "source": "tool-agent",
                "error": err,
                "reason": err,
            }

        # Generic metrics via grafana MCP only when UID configured
        if self._prom_uid and query_ref in {
            "k8s.endpoints.ready",
            "k8s.deployment.available",
            "k8s.pod.ready",
            "grafana.prom.error_rate",
            "grafana.loki.no_fatal",
            "redis.service.alive",
        }:
            ns = variables.get("namespace") or "default"
            svc = _service_name(variables) or ".*"
            expr = (
                f'max(redis_up{{namespace="{ns}",pod=~"{svc}-.*"}}) '
                f'or (count(container_memory_working_set_bytes{{namespace="{ns}",'
                f'pod=~"{svc}-.*",container!="",container!="POD"}}) > bool 0) '
                f"or vector(0)"
            )
            try:
                out = self._post(
                    "/api/v1/tools/execute",
                    {
                        "intent": {
                            "backend": "grafana",
                            "operation": "query_metrics",
                            "params": {
                                "expr": expr,
                                "datasourceUid": self._prom_uid,
                            },
                            "read_only": True,
                            "confidence": 1.0,
                            "rationale": f"Gate A verify {query_ref}",
                        },
                        "include_summary": False,
                        "read_only": True,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                err = str(exc)[:300]
                return {
                    "pass": False,
                    "query_ref": query_ref,
                    "source": "tool-agent:grafana.query_metrics",
                    "error": err,
                    "reason": f"Grafana query_metrics failed for {query_ref}: {err}",
                }
            # Fail closed unless we can parse a positive scalar — keep conservative
            raw = json.dumps(out, default=str)
            err = "grafana metric parse not configured; use OBSERVE_PROVIDER=prometheus"
            return {
                "pass": False,
                "query_ref": query_ref,
                "source": "tool-agent:grafana.query_metrics",
                "error": err,
                "reason": err,
                "raw_snippet": raw[:400],
            }

        err = (
            f"tool-agent cannot handle query_ref={query_ref} for service="
            f"{_service_name(variables)!r}; set OBSERVE_PROVIDER=prometheus"
        )
        return {
            "pass": False,
            "query_ref": query_ref,
            "source": "tool-agent",
            "error": err,
            "reason": err,
        }


class PreferToolAgentObservability:
    """
    Use tool-agent only for redis service-alive; endpoint readiness → Prometheus.

    Previously routed all redis alerts (including k8s.endpoints.ready) to redis.info,
    which falsely marked endpoint readiness as passed. That behavior is intentionally gone.
    """

    def __init__(self, primary: Any, fallback: Any) -> None:
        self._primary = primary
        self._fallback = fallback

    def query(self, *, query_ref: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = dict(variables or {})
        if tool_agent_owns_query(query_ref=query_ref, variables=variables):
            return self._primary.query(query_ref=query_ref, variables=variables)
        return self._fallback.query(query_ref=query_ref, variables=variables)
