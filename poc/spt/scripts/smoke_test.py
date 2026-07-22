#!/usr/bin/env python3
"""CLI runner for Phase 0 smoke test (same logic as POST /smoke)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def _main() -> int:
    from app.octoperf_ops import ping, run_smoke_test

    if len(sys.argv) > 1 and sys.argv[1] == "ping":
        result = await ping()
        print(json.dumps(result, indent=2))
        return 0

    result = await run_smoke_test()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
