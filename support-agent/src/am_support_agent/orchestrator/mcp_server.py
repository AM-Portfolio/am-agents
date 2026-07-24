"""Official Temporal MCP Server for Support Agent using FastMCP & Temporal Python SDK."""

from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from temporalio.client import Client

mcp = FastMCP("TemporalOfficialMCP")

_target = os.getenv("TEMPORAL_HOST") or "localhost:7233"
_namespace = os.getenv("TEMPORAL_NAMESPACE") or "default"


async def _get_client() -> Client:
    return await Client.connect(_target, namespace=_namespace)


@mcp.tool()
async def temporal_list_workflows(status: str = "Running", query: str | None = None) -> dict[str, Any]:
    """List or search Temporal workflow executions by status or query string."""
    client = await _get_client()
    if status and not query:
        query = f'ExecutionStatus = "{status}"'

    results = []
    if query:
        async for wf in client.list_workflows(query):
            results.append({
                "workflow_id": wf.id,
                "run_id": wf.run_id,
                "type": wf.type,
                "status": wf.status.name if wf.status else "UNKNOWN",
                "start_time": str(wf.start_time),
            })
            if len(results) >= 50:
                break
    else:
        async for wf in client.list_workflows():
            results.append({
                "workflow_id": wf.id,
                "run_id": wf.run_id,
                "type": wf.type,
                "status": wf.status.name if wf.status else "UNKNOWN",
                "start_time": str(wf.start_time),
            })
            if len(results) >= 50:
                break
    return {"count": len(results), "workflows": results}


@mcp.tool()
async def temporal_describe_workflow(workflow_id: str, run_id: str | None = None) -> dict[str, Any]:
    """Get detailed state, execution status, and history length of a Temporal workflow."""
    client = await _get_client()
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    desc = await handle.describe()
    return {
        "workflow_id": desc.id,
        "run_id": desc.run_id,
        "type": desc.type,
        "status": desc.status.name,
        "start_time": str(desc.start_time),
        "close_time": str(desc.close_time) if desc.close_time else None,
        "history_length": desc.history_length,
    }


@mcp.tool()
async def temporal_signal_workflow(
    workflow_id: str, signal_name: str, arg: Any = None, run_id: str | None = None
) -> dict[str, Any]:
    """Send a signal to a running Temporal workflow execution."""
    client = await _get_client()
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    if arg is not None:
        await handle.signal(signal_name, arg)
    else:
        await handle.signal(signal_name)
    return {"action": "signaled", "workflow_id": workflow_id, "signal_name": signal_name}


@mcp.tool()
async def temporal_query_workflow(
    workflow_id: str, query_name: str, run_id: str | None = None
) -> dict[str, Any]:
    """Query a live running workflow's query handler (e.g. status or hitl)."""
    client = await _get_client()
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    res = await handle.query(query_name)
    return {"workflow_id": workflow_id, "query_name": query_name, "result": res}


@mcp.tool()
async def temporal_terminate_workflow(
    workflow_id: str, reason: str = "Terminated via Temporal MCP", run_id: str | None = None
) -> dict[str, Any]:
    """Terminate a running Temporal workflow execution."""
    client = await _get_client()
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    await handle.terminate(reason=reason)
    return {"action": "terminated", "workflow_id": workflow_id, "reason": reason}


def main() -> None:
    global _target, _namespace
    parser = argparse.ArgumentParser(description="Official Temporal MCP Server")
    parser.add_argument("--target", default=_target, help="Temporal gRPC target (e.g. localhost:7233)")
    parser.add_argument("--namespace", default=_namespace, help="Temporal namespace (default: default)")
    args = parser.parse_args()
    _target = args.target
    _namespace = args.namespace
    mcp.run()


if __name__ == "__main__":
    main()
