#!/usr/bin/env python3
"""Smoke-test db-agent preprod API (health, plan, query)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8140"


def call(
    method: str, path: str, body: dict | None = None, extra_headers: dict | None = None
) -> tuple[int, dict | str]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
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
    failures = 0

    for label, method, path, body, headers in [
        ("health", "GET", "/health", None, {}),
        ("ready", "GET", "/ready", None, {}),
        (
            "plan-qdrant",
            "POST",
            "/api/v1/db/plan",
            {"query": "list qdrant collections", "backend": "qdrant"},
            {},
        ),
        (
            "query-qdrant",
            "POST",
            "/api/v1/db/query",
            {"query": "list qdrant collections", "backend": "qdrant"},
            {},
        ),
    ]:
        try:
            status, payload = call(method, path, body, headers)
            ok = 200 <= status < 300
            print(f"\n[{label}] HTTP {status} {'OK' if ok else 'FAIL'}")
            print(json.dumps(payload, indent=2)[:2000])
            if not ok:
                failures += 1
        except Exception as exc:
            print(f"\n[{label}] ERROR: {exc}")
            failures += 1

    if failures:
        print(f"\n{failures} check(s) failed.", file=sys.stderr)
        return 1
    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
