#!/usr/bin/env python3
"""Broader preprod API test suite for db-agent."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8140"

CASES = [
    ("ready", "GET", "/ready", None),
    (
        "plan-qdrant",
        "POST",
        "/api/v1/db/plan",
        {"query": "list qdrant collections", "backend": "qdrant"},
    ),
    (
        "query-qdrant",
        "POST",
        "/api/v1/db/query",
        {"query": "list qdrant collections", "backend": "qdrant"},
    ),
    (
        "plan-mongo",
        "POST",
        "/api/v1/db/plan",
        {"query": "list mongo databases", "backend": "mongodb"},
    ),
    (
        "query-mongo",
        "POST",
        "/api/v1/db/query",
        {"query": "list mongo databases", "backend": "mongodb"},
    ),
    (
        "plan-redis",
        "POST",
        "/api/v1/db/plan",
        {"query": "redis info server", "backend": "redis"},
    ),
    (
        "query-redis",
        "POST",
        "/api/v1/db/execute",
        {
            "intent": {
                "backend": "redis",
                "operation": "info",
                "params": {"section": "server"},
                "read_only": True,
                "confidence": 1.0,
                "rationale": "preprod test",
            }
        },
    ),
    (
        "plan-postgres",
        "POST",
        "/api/v1/db/plan",
        {"query": "list postgres tables", "backend": "postgres"},
    ),
    (
        "query-postgres",
        "POST",
        "/api/v1/db/query",
        {"query": "show postgres databases", "backend": "postgres"},
    ),
]


def call(method: str, path: str, body: dict | None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url=f"{BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def main() -> int:
    passed = failed = 0
    print(f"db-agent preprod API tests -> {BASE}\n")

    for label, method, path, body in CASES:
        try:
            status, payload = call(method, path, body)
            ok = 200 <= status < 300
            mark = "PASS" if ok else "FAIL"
            print(f"[{mark}] {label} HTTP {status}")
            if isinstance(payload, dict):
                if label == "ready":
                    print(f"       llm_routing={payload.get('llm_routing')} llm_reachable={payload.get('llm_reachable')}")
                elif "plan" in label and "intent" in payload:
                    intent = payload["intent"]
                    print(f"       backend={intent.get('backend')} op={intent.get('operation')} conf={intent.get('confidence')}")
                elif "query" in label:
                    print(f"       backend={payload.get('backend')} summary={str(payload.get('summary',''))[:80]}")
                    if payload.get("warnings"):
                        print(f"       warnings={payload['warnings']}")
                    if payload.get("gateway_trace_id"):
                        print(f"       gateway_trace_id={payload['gateway_trace_id']}")
                elif not ok:
                    print(f"       {json.dumps(payload)[:300]}")
            else:
                print(f"       {str(payload)[:200]}")
            if ok:
                passed += 1
            else:
                failed += 1
        except Exception as exc:
            print(f"[FAIL] {label} ERROR: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
