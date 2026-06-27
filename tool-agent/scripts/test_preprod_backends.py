#!/usr/bin/env python3
"""Preprod integration: health, MCP bridge, plan/query all backends."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import httpx

BASE = os.environ.get("TOOL_AGENT_BASE_URL", "https://am.asrax.in/tools").rstrip("/")
TIMEOUT = 120.0
CALLER = os.environ.get("TOOL_AGENT_CALLER", "preprod-smoke")
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Agent-Caller": CALLER,
}

PLAN_CASES = [
    ("plan-mongodb", {"query": "list mongo databases", "backend": "mongodb"}),
    ("plan-postgres", {"query": "postgres search schema portfolio", "backend": "postgres"}),
    ("plan-redis", {"query": "redis info", "backend": "redis"}),
    ("plan-kafka", {"query": "list kafka topics", "backend": "kafka"}),
    ("plan-qdrant", {"query": "list qdrant collections", "backend": "qdrant"}),
    ("plan-grafana", {"query": "list grafana datasources", "backend": "grafana"}),
    ("plan-vault", {"query": "list vault secrets under preprod infra", "backend": "vault"}),
]

QUERY_CASES = [
    ("query-redis-info", {"query": "redis info server", "backend": "redis", "read_only": True}),
    ("query-redis-scan", {"query": "scan redis keys *", "backend": "redis", "read_only": True}),
    (
        "query-postgres-schema",
        {"query": "search postgres schema for portfolio tables", "backend": "postgres", "read_only": True},
    ),
    (
        "query-mongodb-databases",
        {"query": "list mongo databases", "backend": "mongodb", "read_only": True},
    ),
    (
        "query-kafka-topics",
        {"query": "list kafka topics", "backend": "kafka", "read_only": True},
    ),
    (
        "query-qdrant-collections",
        {"query": "list qdrant collections", "backend": "qdrant", "read_only": True},
    ),
    (
        "query-grafana-datasources",
        {"query": "list grafana datasources", "backend": "grafana", "read_only": True},
    ),
    (
        "query-vault-list",
        {"query": "list vault secrets under preprod infra", "backend": "vault", "read_only": True},
    ),
    (
        "query-vault-read",
        {"query": "read vault postgres secret in preprod", "backend": "vault", "read_only": True},
    ),
    (
        "query-vault-mounts",
        {"query": "list vault mounts", "backend": "vault", "read_only": True},
    ),
]


def http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        if method == "GET":
            resp = client.get(f"{BASE}{path}", headers=HEADERS)
        else:
            resp = client.post(f"{BASE}{path}", headers=HEADERS, json=body)
    try:
        payload: dict | str = resp.json()
    except Exception:
        payload = resp.text
    return resp.status_code, payload


def load_bridge():
    bridge_path = Path(__file__).resolve().parent / "mcp_stdio_bridge.py"
    spec = importlib.util.spec_from_file_location("mcp_stdio_bridge", bridge_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mcp_stdio_bridge"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    passed = failed = 0
    print(f"Preprod tool-agent tests -> {BASE} (caller={CALLER})\n")

    for label, path in [("health", "/health"), ("ready", "/ready")]:
        status, payload = http("GET", path)
        ok = status == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
        print(f"  {'PASS' if ok else 'FAIL'}  {label} [{status}]")
        passed += ok
        failed += not ok

    os.environ["TOOL_AGENT_BASE_URL"] = BASE
    os.environ["TOOL_AGENT_CALLER"] = CALLER
    bridge = load_bridge()
    for name, fn, args in [
        ("mcp-bridge-health", bridge.tool_agent_health, ()),
        ("mcp-bridge-plan-redis", bridge.tool_agent_plan, ("redis info", "redis", True)),
    ]:
        try:
            raw = fn(*args)
            data = json.loads(raw)
            ok = data.get("status_code") == 200
            print(f"  {'PASS' if ok else 'FAIL'}  {name} [{data.get('status_code')}]")
            if ok:
                intent = (data.get("body") or {}).get("intent") or {}
                if intent:
                    print(f"         intent: {intent.get('backend')}.{intent.get('operation')}")
            else:
                print(f"         {raw[:300]}")
        except RuntimeError as exc:
            ok = False
            print(f"  FAIL  {name} {exc}")
        passed += ok
        failed += not ok

    for label, body in PLAN_CASES:
        status, payload = http("POST", "/api/v1/tools/plan", body)
        ok = status == 200 and isinstance(payload, dict) and bool(payload.get("intent"))
        if ok:
            intent = payload["intent"]
            print(f"  PASS  {label} -> {intent.get('backend')}.{intent.get('operation')}")
        else:
            detail = payload.get("detail") if isinstance(payload, dict) else payload
            print(f"  FAIL  {label} [{status}] {str(detail)[:200]}")
        passed += ok
        failed += not ok

    for label, body in QUERY_CASES:
        status, payload = http("POST", "/api/v1/tools/query", body)
        ok = status == 200 and isinstance(payload, dict) and bool(payload.get("backend"))
        if ok:
            print(
                f"  PASS  {label} -> {payload.get('backend')}.{payload.get('operation')} "
                f"via {payload.get('tool_source')} ({payload.get('duration_ms')}ms)"
            )
            data = payload.get("data")
            preview = json.dumps(data, default=str)[:180] if data is not None else ""
            if preview:
                print(f"         data: {preview}...")
        else:
            detail = payload.get("detail") if isinstance(payload, dict) else payload
            print(f"  FAIL  {label} [{status}] {str(detail)[:250]}")
        passed += ok
        failed += not ok

    print(f"\n{passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
