"""In-cluster OctoPerf MCP mock for Phase 0 E2E (no OAuth).

Swap OCTOPERF_MCP_URL to https://api.octoperf.com/mcp + bearer token for real SaaS.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("octoperf-mock", instructions="Mock OctoPerf MCP for SPT POC verification")

_runs: dict[str, dict[str, Any]] = {}


@mcp.tool(name="import_virtual_user_k6")
def import_virtual_user_k6(
    source: str = "k6",
    content: str = "",
    filename: str = "script.js",
    workspaceId: str | None = None,
    projectId: str | None = None,
) -> dict[str, Any]:
    vu_id = f"vu-k6-{uuid.uuid4().hex[:8]}"
    return {
        "virtualUserId": vu_id,
        "source": source,
        "filename": filename,
        "bytes": len(content),
        "workspaceId": workspaceId,
        "projectId": projectId,
        "status": "imported",
        "uiUrl": "https://app.octoperf.com/mock/virtual-user/" + vu_id,
    }


@mcp.tool(name="import_virtual_user_playwright")
def import_virtual_user_playwright(
    source: str = "playwright",
    content: str = "",
    filename: str = "spec.ts",
    workspaceId: str | None = None,
    projectId: str | None = None,
) -> dict[str, Any]:
    vu_id = f"vu-pw-{uuid.uuid4().hex[:8]}"
    return {
        "virtualUserId": vu_id,
        "source": source,
        "filename": filename,
        "bytes": len(content),
        "status": "imported",
        "uiUrl": "https://app.octoperf.com/mock/virtual-user/" + vu_id,
    }


@mcp.tool(name="run_bench_scenario")
def run_bench_scenario(
    vus: int = 5,
    duration: str = "1m",
    virtualUserId: str | None = None,
    projectId: str | None = None,
) -> dict[str, Any]:
    run_id = f"bench-{uuid.uuid4().hex[:10]}"
    _runs[run_id] = {
        "started": time.monotonic(),
        "vus": vus,
        "duration": duration,
        "virtualUserId": virtualUserId,
        "projectId": projectId,
        "status": "running",
    }
    return {
        "runId": run_id,
        "status": "running",
        "vus": vus,
        "duration": duration,
        "virtualUserId": virtualUserId,
        "uiUrl": f"https://app.octoperf.com/mock/bench/{run_id}",
    }


@mcp.tool(name="get_run_status")
def get_run_status(runId: str) -> dict[str, Any]:
    run = _runs.get(runId)
    if not run:
        return {"runId": runId, "status": "failed", "error": "unknown run"}
    elapsed = time.monotonic() - run["started"]
    if elapsed < 8:
        run["status"] = "running"
    else:
        run["status"] = "completed"
    return {"runId": runId, "status": run["status"], "elapsedSeconds": round(elapsed, 1)}


@mcp.tool(name="get_bench_report")
def get_bench_report(runId: str) -> dict[str, Any]:
    run = _runs.get(runId, {})
    vus = run.get("vus", 5)
    return {
        "runId": runId,
        "status": "completed",
        "throughput": {"requestsPerSecond": round(42.5 * vus / 5, 2)},
        "errorRate": 0.0,
        "responseTime": {
            "avg": 118,
            "p50": 95,
            "p90": 210,
            "p99": 380,
            "min": 45,
            "max": 520,
        },
        "hits": int(42.5 * vus / 5 * 60),
        "errors": 0,
        "uiUrl": f"https://app.octoperf.com/mock/bench/{runId}/report",
    }


@mcp.tool(name="list_workspaces")
def list_workspaces() -> dict[str, Any]:
    return {
        "workspaces": [
            {"id": "ws-mock-001", "name": "SPT POC Mock Workspace"},
        ]
    }


app = mcp.streamable_http_app()
