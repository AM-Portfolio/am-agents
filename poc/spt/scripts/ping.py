#!/usr/bin/env python3
"""MCP connectivity ping only."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def _main() -> int:
    from app.octoperf_ops import ping

    try:
        result = await ping()
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        detail = str(exc)
        if exc.__cause__:
            detail = f"{detail} | cause: {exc.__cause__}"
        print(json.dumps({"status": "fail", "error": detail, "mcp_url": __import__("app.config", fromlist=["settings"]).settings.octoperf_mcp_url}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
