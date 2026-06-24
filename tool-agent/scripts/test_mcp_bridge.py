#!/usr/bin/env python3
"""Smoke test tool-agent HTTP + MCP bridge helpers against live preprod."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("TOOL_AGENT_BASE_URL", "https://am.asrax.in/tools")

_bridge_path = Path(__file__).resolve().parent / "mcp_stdio_bridge.py"
_spec = importlib.util.spec_from_file_location("mcp_stdio_bridge", _bridge_path)
assert _spec and _spec.loader
_bridge = importlib.util.module_from_spec(_spec)
sys.modules["mcp_stdio_bridge"] = _bridge
_spec.loader.exec_module(_bridge)

_base_url = _bridge._base_url
tool_agent_health = _bridge.tool_agent_health
tool_agent_plan = _bridge.tool_agent_plan


def _ok(name: str, raw: str) -> bool:
    data = json.loads(raw)
    status = data.get("status_code")
    body = data.get("body") or {}
    print(f"[{name}] HTTP {status}")
    if status != 200:
        print(raw[:500])
        return False
    if name == "health" and body.get("status") != "ok":
        print(raw[:500])
        return False
    if name == "plan" and not body.get("intent"):
        print(raw[:500])
        return False
    print(json.dumps(body, indent=2)[:400])
    return True


def main() -> int:
    print(f"tool-agent MCP bridge smoke test -> {_base_url()}\n")
    passed = 0
    total = 2

    if _ok("health", tool_agent_health()):
        passed += 1

    if _ok(
        "plan",
        tool_agent_plan("list mongo databases", backend="mongodb", read_only=True),
    ):
        passed += 1

    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
