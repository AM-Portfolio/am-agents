#!/usr/bin/env python3
"""Compare plan intent between db-agent (/db) and tool-agent (/tools)."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

AGENT_ROOT = Path(__file__).resolve().parents[1]


def _post(base: str, path: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": e.read().decode()[:300]}


def _plan_key(payload: dict) -> dict:
    intent = payload.get("intent") or {}
    return {
        "backend": intent.get("backend"),
        "operation": intent.get("operation"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy", default="https://am.asrax.in/db")
    parser.add_argument("--target", default="https://am.asrax.in/tools")
    parser.add_argument("--corpus", default=str(AGENT_ROOT / "scripts" / "parity_corpus.yaml"))
    parser.add_argument("--local", action="store_true", help="Skip HTTP; validate corpus only")
    args = parser.parse_args()

    with open(args.corpus, encoding="utf-8") as f:
        corpus = yaml.safe_load(f) or {}
    queries = corpus.get("queries") or []

    if args.local:
        print(f"OK: corpus has {len(queries)} queries")
        return 0

    passed = warned = failed = 0
    for item in queries:
        label = item["label"]
        body = {"query": item["query"], "backend": item.get("backend")}
        _, legacy = _post(args.legacy, "/api/v1/db/plan", body)
        _, target = _post(args.target, "/api/v1/tools/plan", body)
        lk = _plan_key(legacy)
        tk = _plan_key(target)
        if lk == tk and lk.get("backend"):
            passed += 1
            print(f"PASS {label} {lk}")
        elif lk.get("backend") and tk.get("backend"):
            warned += 1
            print(f"WARN {label} legacy={lk} target={tk}")
        else:
            failed += 1
            print(f"FAIL {label} legacy={legacy} target={target}")

    total = passed + warned + failed
    print(f"\n{passed} pass, {warned} warn, {failed} fail / {total}")
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
