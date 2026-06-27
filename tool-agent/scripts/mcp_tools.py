"""Shared MCP tool definitions and HTTP client for tool-agent bridges."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://am-tool-agent.am-apps-preprod.svc.cluster.local:8141"
TIMEOUT_SECONDS = 120.0
MCP_CONTRACT_VERSION = "1.0.0"


def base_url() -> str:
    return os.environ.get("TOOL_AGENT_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def headers() -> dict[str, str]:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    caller = os.environ.get("TOOL_AGENT_CALLER", "").strip()
    if caller:
        h["X-Agent-Caller"] = caller
    return h


def format_result(data: Any, *, status_code: int, stages: list[dict[str, Any]] | None = None) -> str:
    payload: dict[str, Any] = {
        "status_code": status_code,
        "body": data,
        "mcp_contract_version": MCP_CONTRACT_VERSION,
    }
    if stages:
        payload["stages"] = stages
    return json.dumps(payload, indent=2, default=str)


def http_get(path: str) -> str:
    url = f"{base_url()}{path}"
    with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        resp = client.get(url, headers=headers())
    try:
        body: Any = resp.json()
    except Exception:
        body = resp.text
    if resp.status_code >= 400:
        raise RuntimeError(format_result(body, status_code=resp.status_code))
    return format_result(body, status_code=resp.status_code)


def http_post(path: str, payload: dict[str, Any], *, stream: bool = False) -> str:
    url = f"{base_url()}{path}"
    if not stream:
        with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.post(url, headers=headers(), json=payload)
        try:
            body: Any = resp.json()
        except Exception:
            body = resp.text
        if resp.status_code >= 400:
            raise RuntimeError(format_result(body, status_code=resp.status_code))
        return format_result(body, status_code=resp.status_code)

    stages: list[dict[str, Any]] = []
    final_body: Any = None
    status_code = 200
    stream_headers = {**headers(), "Accept": "text/event-stream"}
    with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        with client.stream("POST", url, headers=stream_headers, json=payload) as resp:
            status_code = resp.status_code
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                stages.append(event)
                if event.get("event") == "done":
                    final_body = event.get("response") or event.get("plan") or event.get("data")
                if event.get("event") == "error":
                    final_body = event
            if status_code >= 400:
                raise RuntimeError(format_result(final_body or stages, status_code=status_code, stages=stages))
    return format_result(final_body, status_code=status_code, stages=stages)


def tool_agent_health() -> str:
    return http_get("/health")


def tool_agent_ready() -> str:
    return http_get("/ready")


def tool_agent_list_backends() -> str:
    raw = http_get("/health")
    data = json.loads(raw)
    enabled = (data.get("body") or {}).get("enabled_tools") or []
    return format_result({"backends": enabled}, status_code=data.get("status_code", 200))


def normalize_infra_query(query: str, backend: str | None = None) -> str:
    """Strip kagent-style noise so NL rules route correctly (e.g. read-only → list_topics)."""
    q = query.strip()
    q = re.sub(r"\bread-only\b", " ", q, flags=re.I)
    q = re.sub(r"\breadonly\b", " ", q, flags=re.I)
    if backend:
        q = re.sub(rf"\bbackend\s+{re.escape(backend)}\b", " ", q, flags=re.I)
    q = re.sub(r"\s+", " ", q).strip(" .,")
    if not q:
        return f"list {backend} topics" if backend == "kafka" else f"list {backend or 'infra'}"
    return q


def tool_agent_query_slim(
    query: str,
    backend: str | None = None,
    read_only: bool = True,
    include_summary: bool = True,
    max_rows: int = 100,
) -> str:
    """Query tool-agent and return a slim JSON string for LLM consumption."""
    normalized = normalize_infra_query(query, backend)
    raw = tool_agent_query(
        normalized,
        backend=backend,
        read_only=read_only,
        include_summary=include_summary,
        max_rows=max_rows,
    )
    return json.dumps(_slim_for_agent(json.loads(raw)), indent=2, default=str)


def kafka_list_topics(max_rows: int = 100) -> str:
    """List Kafka topics in preprod (read-only)."""
    return tool_agent_query_slim("list kafka topics", backend="kafka", max_rows=max_rows)


def mongodb_list_databases(max_rows: int = 100) -> str:
    """List MongoDB databases in preprod (read-only)."""
    return tool_agent_query_slim("list mongodb databases", backend="mongodb", max_rows=max_rows)


def tool_agent_plan(query: str, backend: str | None = None, read_only: bool = True) -> str:
    body: dict[str, Any] = {"query": normalize_infra_query(query, backend), "read_only": read_only}
    if backend:
        body["backend"] = backend
    use_stream = os.environ.get("TOOL_AGENT_MCP_USE_STREAM", "true").lower() in ("1", "true", "yes")
    path = "/api/v1/tools/plan/stream" if use_stream else "/api/v1/tools/plan"
    return http_post(path, body, stream=use_stream)


def tool_agent_query(
    query: str,
    backend: str | None = None,
    read_only: bool = True,
    include_summary: bool = True,
    max_rows: int = 100,
) -> str:
    body: dict[str, Any] = {
        "query": normalize_infra_query(query, backend),
        "read_only": read_only,
        "include_summary": include_summary,
        "max_rows": max_rows,
    }
    if backend:
        body["backend"] = backend
    use_stream = os.environ.get("TOOL_AGENT_MCP_USE_STREAM", "true").lower() in ("1", "true", "yes")
    path = "/api/v1/tools/query/stream" if use_stream else "/api/v1/tools/query"
    return http_post(path, body, stream=use_stream)


def _extract_intent(obj: dict[str, Any]) -> dict[str, Any]:
    """Accept raw intent, plan body, or MCP wrapper from the LLM."""
    if "intent" in obj and isinstance(obj["intent"], dict):
        return obj["intent"]
    body = obj.get("body")
    if isinstance(body, dict):
        if "intent" in body and isinstance(body["intent"], dict):
            return body["intent"]
        if body.get("backend") and body.get("operation"):
            return body
    if obj.get("backend") and obj.get("operation"):
        return obj
    raise ValueError(
        "Could not find intent object. Pass plan.body.intent or the intent dict "
        "(backend, operation, params, read_only)."
    )


def _slim_for_agent(data: Any) -> Any:
    """Reduce payload size so the LLM quotes real data instead of inventing rows."""
    if not isinstance(data, dict):
        return data
    body = data.get("body") if "body" in data and "status_code" in data else data
    if not isinstance(body, dict):
        return data
    inner = body.get("data") if isinstance(body.get("data"), dict) else body
    if isinstance(inner, dict) and "topics" in inner:
        topics = inner["topics"]
        names = [t.get("name") if isinstance(t, dict) else t for t in topics]
        return {
            "backend": body.get("backend", "kafka"),
            "operation": body.get("operation", "list_topics"),
            "topic_count": len(names),
            "topics": names[:50],
        }
    if isinstance(inner, dict) and "rows" in inner:
        return {
            "backend": body.get("backend"),
            "operation": body.get("operation"),
            "row_count": len(inner.get("rows") or []),
            "rows": (inner.get("rows") or [])[:20],
            "summary": body.get("summary"),
        }
    return body


def tool_agent_execute(intent_json: str, include_summary: bool = False, max_rows: int = 100) -> str:
    try:
        parsed = json.loads(intent_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"intent_json must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("intent_json must be a JSON object")
    intent = _extract_intent(parsed)
    body: dict[str, Any] = {
        "intent": intent,
        "include_summary": include_summary,
        "max_rows": max_rows,
    }
    use_stream = os.environ.get("TOOL_AGENT_MCP_USE_STREAM", "true").lower() in ("1", "true", "yes")
    path = "/api/v1/tools/execute/stream" if use_stream else "/api/v1/tools/execute"
    raw = http_post(path, body, stream=use_stream)
    slim = _slim_for_agent(json.loads(raw))
    return json.dumps(slim, indent=2, default=str)


def tool_agent_plan_and_execute(
    query: str,
    backend: str | None = None,
    read_only: bool = True,
    max_rows: int = 100,
) -> str:
    """One MCP call: plan + execute. Best for kagent read-only infra queries."""
    plan_raw = json.loads(tool_agent_plan(query, backend=backend, read_only=read_only))
    plan_body = plan_raw.get("body") or plan_raw
    intent = _extract_intent(plan_body if isinstance(plan_body, dict) else plan_raw)
    exec_raw = tool_agent_execute(json.dumps(intent), include_summary=True, max_rows=max_rows)
    return exec_raw
