#!/usr/bin/env python3
"""Stdio MCP bridge: Cursor mcp.json -> tool-agent HTTP API."""

from __future__ import annotations

import sys
from pathlib import Path

_agent_root = Path(__file__).resolve().parents[1]
sys.path = [p for p in sys.path if Path(p).resolve() != _agent_root]
import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_BASE_URL = "https://am.asrax.in/tools"
TIMEOUT_SECONDS = 60.0

mcp = FastMCP("AM Tool Agent")


def _base_url() -> str:
    return os.environ.get("TOOL_AGENT_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    caller = os.environ.get("TOOL_AGENT_CALLER", "").strip()
    if caller:
        headers["X-Agent-Caller"] = caller
    return headers


def _format_result(data: Any, *, status_code: int) -> str:
    payload = {"status_code": status_code, "body": data}
    return json.dumps(payload, indent=2, default=str)


def _http_get(path: str) -> str:
    url = f"{_base_url()}{path}"
    with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        resp = client.get(url, headers=_headers())
    try:
        body: Any = resp.json()
    except Exception:
        body = resp.text
    if resp.status_code >= 400:
        raise RuntimeError(_format_result(body, status_code=resp.status_code))
    return _format_result(body, status_code=resp.status_code)


def _http_post(path: str, payload: dict[str, Any]) -> str:
    url = f"{_base_url()}{path}"
    with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        resp = client.post(url, headers=_headers(), json=payload)
    try:
        body: Any = resp.json()
    except Exception:
        body = resp.text
    if resp.status_code >= 400:
        raise RuntimeError(_format_result(body, status_code=resp.status_code))
    return _format_result(body, status_code=resp.status_code)


@mcp.tool()
def tool_agent_health() -> str:
    """Check tool-agent health (enabled tools, env)."""
    return _http_get("/health")


@mcp.tool()
def tool_agent_ready() -> str:
    """Check tool-agent readiness (registry, LLM, Langfuse)."""
    return _http_get("/ready")


@mcp.tool()
def tool_agent_plan(query: str, backend: str | None = None, read_only: bool = True) -> str:
    """Parse NL query into intent only (no execution). backend e.g. mongodb, redis, kafka."""
    body: dict[str, Any] = {"query": query, "read_only": read_only}
    if backend:
        body["backend"] = backend
    return _http_post("/api/v1/tools/plan", body)


@mcp.tool()
def tool_agent_query(
    query: str,
    backend: str | None = None,
    read_only: bool = True,
    include_summary: bool = True,
    max_rows: int = 100,
) -> str:
    """Run NL query end-to-end (parse, resolve, execute, optional summary)."""
    body: dict[str, Any] = {
        "query": query,
        "read_only": read_only,
        "include_summary": include_summary,
        "max_rows": max_rows,
    }
    if backend:
        body["backend"] = backend
    return _http_post("/api/v1/tools/query", body)


@mcp.tool()
def tool_agent_execute(intent_json: str, include_summary: bool = False, max_rows: int = 100) -> str:
    """Execute structured intent JSON. intent_json: IntentDocument fields (backend, operation, params, ...)."""
    try:
        intent = json.loads(intent_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"intent_json must be valid JSON: {exc}") from exc
    if not isinstance(intent, dict):
        raise ValueError("intent_json must be a JSON object")
    body: dict[str, Any] = {
        "intent": intent,
        "include_summary": include_summary,
        "max_rows": max_rows,
    }
    return _http_post("/api/v1/tools/execute", body)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
