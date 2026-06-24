#!/usr/bin/env python3
"""Complex MongoDB queries against running db-agent API."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8140"

QUERIES = [
    (
        "count-portfolios",
        "POST",
        "/api/v1/db/query",
        {
            "query": "How many documents are in the portfolios collection in portfolio-db MongoDB?",
            "backend": "mongodb",
            "include_summary": True,
        },
    ),
    (
        "list-collections",
        "POST",
        "/api/v1/db/query",
        {
            "query": "list all collections in portfolio-db mongodb database",
            "backend": "mongodb",
        },
    ),
    (
        "find-portfolios",
        "POST",
        "/api/v1/db/execute",
        {
            "intent": {
                "backend": "mongodb",
                "operation": "find",
                "params": {
                    "database": "portfolio-db",
                    "collection": "portfolios",
                    "filter": {},
                },
                "read_only": True,
                "confidence": 1.0,
                "rationale": "complex test: sample portfolio documents",
            },
            "include_summary": True,
            "max_rows": 5,
        },
    ),
    (
        "count-with-filter",
        "POST",
        "/api/v1/db/execute",
        {
            "intent": {
                "backend": "mongodb",
                "operation": "count_documents",
                "params": {
                    "database": "portfolio-db",
                    "collection": "portfolios",
                    "filter": {},
                },
                "read_only": True,
                "confidence": 1.0,
                "rationale": "complex test: total portfolio count via execute",
            },
            "include_summary": True,
        },
    ),
]


def call(method: str, path: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main() -> int:
    failed = 0
    print(f"Mongo complex tests -> {BASE}\n")
    for label, method, path, body in QUERIES:
        status, payload = call(method, path, body)
        ok = 200 <= status < 300
        print(f"[{'OK' if ok else 'FAIL'}] {label} HTTP {status}")
        if ok and "response" in payload:
            r = payload["response"]
            print(f"  op={r.get('operation')} conf={r.get('confidence')} parse={r.get('parse_source')}")
            print(f"  summary: {str(r.get('summary'))[:120]}")
            data = r.get("data")
            print(f"  data: {json.dumps(data, default=str)[:400]}")
            print(f"  request_id: {r.get('request_id')}")
        elif ok and "plan" in payload:
            p = payload["plan"]
            print(f"  intent: {json.dumps(p.get('intent', {}), default=str)[:300]}")
        elif not ok:
            print(f"  error: {json.dumps(payload)[:300]}")
        else:
            print(f"  {json.dumps(payload, default=str)[:400]}")
        print()
        if not ok:
            failed += 1
    print(f"\n{len(QUERIES) - failed}/{len(QUERIES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
