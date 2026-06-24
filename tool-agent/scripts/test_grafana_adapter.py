#!/usr/bin/env python3
"""Integration test: grafana plugin adapter via port-forwarded MCP."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("GRAFANA_MCP_URL", "http://127.0.0.1:18000/mcp")

from app.schema.loader import reset_schema_catalog  # noqa: E402
from tools.grafana.adapter import GrafanaAdapter  # noqa: E402


async def main() -> int:
    reset_schema_catalog()
    adapter = GrafanaAdapter()
    ds = await adapter.execute("list_datasources", {}, read_only=True, max_rows=10)
    print("list_datasources ok:", str(ds)[:400])

    logs = await adapter.execute(
        "query_logs",
        {
            "datasourceUid": "P8E80F9AEF21F6940",
            "query": '{namespace="am-apps-preprod"}',
            "start": "now-15m",
            "end": "now",
        },
        read_only=True,
        max_rows=5,
    )
    print("query_logs ok:", str(logs)[:800])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
