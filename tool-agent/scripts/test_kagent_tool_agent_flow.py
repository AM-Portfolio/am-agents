#!/usr/bin/env python3
"""Smoke test: tool-agent plan flow (HTTP API or kagent MCP bridge)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow importing mcp_tools from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcp_tools  # noqa: E402


def test_api_plan() -> bool:
    print(f"API base: {mcp_tools.base_url()}")
    print(f"Caller: {os.environ.get('TOOL_AGENT_CALLER', '(none)')}\n")

    health = json.loads(mcp_tools.tool_agent_health())
    if health.get("status_code") != 200:
        print("FAIL health", health)
        return False
    print("OK  tool_agent_health")

    backends = json.loads(mcp_tools.tool_agent_list_backends())
    names = (backends.get("body") or {}).get("backends") or []
    print(f"OK  backends: {', '.join(names[:8])}{'…' if len(names) > 8 else ''}")

    plan = json.loads(
        mcp_tools.tool_agent_plan(
            "list kafka topics",
            backend="kafka",
            read_only=True,
        )
    )
    if plan.get("status_code") != 200:
        print("FAIL plan", plan)
        return False
    body = plan.get("body") or {}
    intent = body.get("intent") or body
    if isinstance(intent, dict) and "intent" in intent:
        intent = intent["intent"]
    if not intent:
        print("FAIL plan missing intent", json.dumps(body, indent=2)[:600])
        return False
    print("OK  tool_agent_plan intent:", json.dumps(intent, indent=2)[:400])

    execute = json.loads(
        mcp_tools.tool_agent_execute(json.dumps(intent), include_summary=True, max_rows=20)
    )
    if execute.get("status_code") != 200:
        print("FAIL execute", execute)
        return False
    print("OK  tool_agent_execute (truncated):", json.dumps(execute.get("body"), indent=2)[:500])
    return True


def test_mcp_http(mcp_url: str) -> bool:
    try:
        import httpx
    except ImportError:
        print("SKIP MCP HTTP test (pip install httpx)")
        return True

    print(f"MCP URL: {mcp_url}\n")
    # FastMCP streamable-http exposes JSON-RPC at /mcp — list tools via initialize is heavy;
    # hit health via direct tool-agent if MCP pod only proxies tools.
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(mcp_url.replace("/mcp", "/health") if mcp_url.endswith("/mcp") else mcp_url)
    if resp.status_code == 404:
        print("OK  MCP pod has no /health (expected) — use API test against tool-agent")
        return test_api_plan()
    print(f"MCP probe HTTP {resp.status_code}")
    return resp.status_code < 500


def main() -> int:
    parser = argparse.ArgumentParser(description="Test tool-agent kagent integration flow")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("TOOL_AGENT_BASE_URL", "https://am.asrax.in/tools"),
        help="tool-agent REST base URL",
    )
    parser.add_argument(
        "--caller",
        default=os.environ.get("TOOL_AGENT_CALLER", "kagent-test"),
        help="X-Agent-Caller header",
    )
    parser.add_argument(
        "--mcp-url",
        default="",
        help="Optional kagent MCP bridge URL (e.g. http://127.0.0.1:8085/mcp)",
    )
    args = parser.parse_args()

    os.environ["TOOL_AGENT_BASE_URL"] = args.base_url.rstrip("/")
    os.environ["TOOL_AGENT_CALLER"] = args.caller

    ok = test_mcp_http(args.mcp_url) if args.mcp_url else test_api_plan()
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
