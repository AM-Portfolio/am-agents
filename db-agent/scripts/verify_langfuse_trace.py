#!/usr/bin/env python3
"""Verify a Langfuse trace has expected db-agent spans and LLM generations."""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


def auth_headers() -> dict[str, str]:
    token = f"{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}"
    auth = base64.b64encode(token.encode()).decode()
    return {"Authorization": f"Basic {auth}"}


def fetch_trace(trace_id: str, *, retries: int = 15, delay: float = 2.0) -> dict:
    host = settings.LANGFUSE_HOST.rstrip("/")
    url = f"{host}/api/public/traces/{trace_id}"
    headers = auth_headers()
    for attempt in range(1, retries + 1):
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            print(f"[{attempt}/{retries}] trace not indexed yet...")
            time.sleep(delay)
            continue
        raise RuntimeError(f"Langfuse GET trace failed [{resp.status_code}]: {resp.text[:300]}")
    raise RuntimeError(f"Trace {trace_id} not found after {retries} attempts")


def fetch_observations(trace_id: str) -> list[dict]:
    host = settings.LANGFUSE_HOST.rstrip("/")
    url = f"{host}/api/public/observations"
    headers = auth_headers()
    with httpx.Client(timeout=20) as client:
        resp = client.get(url, headers=headers, params={"traceId": trace_id, "limit": 100})
    if resp.status_code != 200:
        raise RuntimeError(f"Langfuse observations failed [{resp.status_code}]: {resp.text[:300]}")
    return resp.json().get("data") or []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_id", help="request_id from db-agent response")
    args = parser.parse_args()

    trace = fetch_trace(args.trace_id)
    obs = fetch_observations(args.trace_id)

    span_names = {o.get("name") for o in obs if o.get("type") == "SPAN"}
    step_names = {
        (o.get("metadata") or {}).get("step")
        for o in obs
        if o.get("type") == "SPAN" and (o.get("metadata") or {}).get("step")
    }
    generations = [o for o in obs if o.get("type") == "GENERATION"]

    print(f"trace: {trace.get('name')} id={args.trace_id}")
    print(f"input: {json.dumps(trace.get('input'), default=str)[:200]}")
    print(f"output: {json.dumps(trace.get('output'), default=str)[:300]}")
    print(f"\nobservations ({len(obs)}):")
    for o in sorted(obs, key=lambda x: x.get("startTime") or ""):
        meta = o.get("metadata") or {}
        src = meta.get("source_name", "")
        suffix = f" [{src}]" if src else ""
        print(f"  [{o.get('type')}] {o.get('name')}{suffix}")

    expected_steps = {"parse_intent", "validate_safety", "execute_tool", "format_response"}
    missing = expected_steps - step_names
    print(f"\ngraph steps present: {sorted(step_names & expected_steps)}")
    if missing:
        print(f"MISSING spans: {sorted(missing)}")
    print(f"LLM generations: {len(generations)} ({', '.join(g.get('name','?') for g in generations) or 'none'})")

    usage_meta = (trace.get("metadata") or {}).get("usage")
    if usage_meta:
        print(f"\ntrace usage totals: {json.dumps(usage_meta, indent=2)}")
    breakdown = (trace.get("metadata") or {}).get("usage_breakdown") or (trace.get("output") or {}).get(
        "usage_breakdown"
    )
    if breakdown:
        print("\nper-step breakdown:")
        for item in breakdown:
            print(
                f"  - {item.get('step')} ({item.get('type')}): "
                f"tokens={item.get('total_tokens')} cost_usd={item.get('cost_usd')}"
            )

    for gen in generations:
        usage = gen.get("usageDetails") or {}
        cost = gen.get("costDetails") or {}
        print(
            f"  gen {gen.get('name')}: in={usage.get('input')} out={usage.get('output')} "
            f"total={usage.get('total')} cost={cost.get('total')}"
        )

    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
