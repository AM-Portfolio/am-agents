#!/usr/bin/env python3
"""Run one MongoDB E2E query using MONGODB_URI from .env.preprod (port-forward)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ENV_FILE_PATH", str(ROOT / ".env.preprod"))

from app.config import settings  # noqa: E402
from app.intent_schema import DbQueryRequest  # noqa: E402
from app.main import app, lifespan  # noqa: E402
from app.runner import run_db_query  # noqa: E402

if not settings.MONGODB_URI:
    raise SystemExit("MONGODB_URI not set — copy .env.example to .env.preprod and fill from Vault")


async def main() -> int:
    query = (
        "How many portfolios are present in the portfolios collection in MongoDB?"
    )
    request = DbQueryRequest(
        query=query,
        backend="mongodb",
        include_summary=True,
        read_only=True,
    )

    async with lifespan(app):
        outcome = await run_db_query(request)
        await asyncio.sleep(4)

    if "error" in outcome:
        print("ERROR:", outcome["error"])
        return 1

    resp = outcome["response"]
    print("request_id:", resp.request_id)
    print("operation:", resp.operation, "| backend:", resp.backend)
    print("confidence:", resp.confidence, "| tool:", resp.tool_source, resp.tool_name)
    print("data:", resp.data)
    print("summary:", resp.summary)
    print("duration_ms:", resp.duration_ms)

    from scripts.verify_langfuse_trace import fetch_observations, fetch_trace

    trace = fetch_trace(resp.request_id, retries=15, delay=2.0)
    obs = fetch_observations(resp.request_id)
    print("\nLangfuse observations:")
    for o in sorted(obs, key=lambda x: x.get("startTime") or ""):
        meta = o.get("metadata") or {}
        src = meta.get("source_name", "")
        print(f"  [{o.get('type')}] {o.get('name')}" + (f" [{src}]" if src else ""))
    usage = (trace.get("metadata") or {}).get("usage")
    if usage:
        print("usage totals:", usage)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
