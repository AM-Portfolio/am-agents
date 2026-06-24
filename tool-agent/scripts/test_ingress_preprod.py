#!/usr/bin/env python3
"""Smoke test tool-agent via HTTPS ingress."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "https://am.asrax.in/tools"

CASES = [
    ("health", "GET", "/health", None),
    ("ready", "GET", "/ready", None),
    ("plan-qdrant", "POST", "/api/v1/tools/plan", {"query": "list qdrant collections", "backend": "qdrant"}),
    ("plan-mongo", "POST", "/api/v1/tools/plan", {"query": "list mongo databases", "backend": "mongodb"}),
    ("plan-redis", "POST", "/api/v1/tools/plan", {"query": "redis info server", "backend": "redis"}),
    ("plan-postgres", "POST", "/api/v1/tools/plan", {"query": "search postgres schema portfolio", "backend": "postgres"}),
    (
        "execute-redis",
        "POST",
        "/api/v1/tools/execute",
        {
            "intent": {
                "backend": "redis",
                "operation": "info",
                "params": {"section": "server"},
                "read_only": True,
                "confidence": 1.0,
                "rationale": "ingress test",
            }
        },
    ),
    (
        "plan-kafka",
        "POST",
        "/api/v1/tools/plan",
        {"query": "list kafka topics", "backend": "kafka"},
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
    print(f"tool-agent HTTPS ingress tests -> {BASE}\n")
    for label, method, path, body in CASES:
        try:
            status, payload = call(method, path, body)
            ok = status < 400
            if ok:
                passed += 1
                print(f"  PASS  {label} [{status}]")
            else:
                failed += 1
                print(f"  FAIL  {label} [{status}] {str(payload)[:200]}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL  {label} [error] {exc}")
    print(f"\n{passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
