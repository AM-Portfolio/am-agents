#!/usr/bin/env python3
"""Run one db-agent query in-process and verify Langfuse trace + spans."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ENV_FILE_PATH", str(ROOT / ".env.preprod"))

from app.intent_schema import DbQueryRequest  # noqa: E402
from app.main import lifespan, app  # noqa: E402
from app.runner import run_db_query  # noqa: E402


async def main() -> int:
    query = (
        "Show Qdrant collection_info for collection ui_patterns — "
        "how many points and what is the status?"
    )
    request = DbQueryRequest(
        query=query,
        backend="qdrant",
        include_summary=True,
        read_only=True,
    )

    async with lifespan(app):
        outcome = await run_db_query(request)
        await asyncio.sleep(3)

    if "error" in outcome:
        print("ERROR:", outcome["error"])
        return 1

    resp = outcome["response"]
    print("request_id:", resp.request_id)
    print("backend:", resp.backend, "operation:", resp.operation)
    print("confidence:", resp.confidence, "tool:", resp.tool_source, resp.tool_name)
    print("duration_ms:", resp.duration_ms)
    print("data:", resp.data)
    print("summary:", resp.summary)

    from scripts.verify_langfuse_trace import fetch_observations, fetch_trace

    trace = fetch_trace(resp.request_id, retries=20, delay=2.0)
    obs = fetch_observations(resp.request_id)
    span_names = {o.get("name") for o in obs if o.get("type") == "SPAN"}
    gens = [o for o in obs if o.get("type") == "GENERATION"]
    expected = {"parse_intent", "validate_safety", "execute_tool", "format_response"}

    print("\nLangfuse trace:", trace.get("name"))
    print("observations:", len(obs))
    for o in sorted(obs, key=lambda x: x.get("startTime") or ""):
        print(f"  [{o.get('type')}] {o.get('name')}")
    print("graph spans OK:", expected <= span_names)
    print("LLM generations:", len(gens))

    return 0 if expected <= span_names else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
