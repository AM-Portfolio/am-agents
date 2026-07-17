"""Observability via tool-agent (redis / grafana) when the query is in its domain."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


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


class ToolAgentObservability:
    """
    Gate A verify through tool-agent HTTP.

    - Redis alerts → redis.info (authoritative process-up check)
    - Other metric refs → optional grafana query_metrics when datasource UID configured
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
            return {
                "pass": False,
                "query_ref": query_ref,
                "source": "tool-agent:redis.info",
                "error": f"tool-agent HTTP {exc.code}: {detail}",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "pass": False,
                "query_ref": query_ref,
                "source": "tool-agent:redis.info",
                "error": f"tool-agent unreachable: {exc}"[:300],
            }

        info = ((out.get("data") or {}) if isinstance(out, dict) else {}).get("info") or {}
        if not isinstance(info, dict):
            info = {}
        version = info.get("redis_version")
        uptime = info.get("uptime_in_seconds")
        ok = bool(version)
        return {
            "pass": ok,
            "query_ref": query_ref,
            "source": "tool-agent:redis.info",
            "value": 1.0 if ok else 0.0,
            "redis_version": version,
            "uptime_in_seconds": uptime,
            "request_id": out.get("request_id") if isinstance(out, dict) else None,
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

        # Redis domain → tool-agent redis (not synthetic VERIFY_FORCE)
        if _is_redis(variables) or "redis" in query_ref.lower():
            return self._redis_info(query_ref=query_ref, variables=variables)

        # Generic metrics via grafana MCP only when UID configured
        if self._prom_uid and query_ref in {
            "k8s.endpoints.ready",
            "k8s.deployment.available",
            "k8s.pod.ready",
            "grafana.prom.error_rate",
            "grafana.loki.no_fatal",
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
                return {
                    "pass": False,
                    "query_ref": query_ref,
                    "source": "tool-agent:grafana.query_metrics",
                    "error": str(exc)[:300],
                }
            # Fail closed unless we can parse a positive scalar — keep conservative
            raw = json.dumps(out, default=str)
            return {
                "pass": False,
                "query_ref": query_ref,
                "source": "tool-agent:grafana.query_metrics",
                "error": "grafana metric parse not configured; use OBSERVE_PROVIDER=prometheus",
                "raw_snippet": raw[:400],
            }

        return {
            "pass": False,
            "query_ref": query_ref,
            "source": "tool-agent",
            "error": (
                f"tool-agent cannot handle query_ref={query_ref} for service="
                f"{_service_name(variables)!r}; set OBSERVE_PROVIDER=prometheus"
            ),
        }


class PreferToolAgentObservability:
    """Use tool-agent for redis (and other domains it owns); else Prometheus."""

    def __init__(self, primary: Any, fallback: Any) -> None:
        self._primary = primary
        self._fallback = fallback

    def query(self, *, query_ref: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = dict(variables or {})
        if _is_redis(variables):
            return self._primary.query(query_ref=query_ref, variables=variables)
        return self._fallback.query(query_ref=query_ref, variables=variables)
