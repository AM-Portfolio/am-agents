"""Official Temporal MCP Server for Support Agent using FastMCP & Temporal Python SDK.

Supports two transport modes:
  - stdio (default): for local IDE MCP client connections (Claude Desktop, Cursor, Antigravity)
  - sse: HTTP/SSE server mode for shared team access via https://mcp.asrax.in/temporal/sse

Usage:
  # Local stdio mode (for ~/.gemini/antigravity-ide/mcp_config.json)
  am-support-agent-mcp --target localhost:7233

  # Remote SSE server mode (for Kubernetes deployment)
  am-support-agent-mcp --transport sse --host 0.0.0.0 --port 8095 --target temporal-frontend.temporal.svc:7233
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from temporalio.client import Client

_target = os.getenv("TEMPORAL_HOST") or "localhost:7233"
_namespace = os.getenv("TEMPORAL_NAMESPACE") or "default"

mcp = FastMCP(
    "TemporalOfficialMCP",
    instructions=(
        "You can use these tools to inspect and manage Temporal workflow executions "
        "on the AM platform cluster. Always double-check the workflow_id before "
        "signalling or terminating."
    ),
)


async def _get_client() -> Client:
    return await Client.connect(_target, namespace=_namespace)


@mcp.tool()
async def temporal_list_workflows(
    status: str = "Running",
    query: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """List or search Temporal workflow executions by status or custom query string.

    Args:
        status: ExecutionStatus filter — Running, Completed, Failed, Canceled, Terminated.
        query: Optional raw Temporal visibility SQL query (overrides status).
        limit: Maximum number of results to return (max 50).
    """
    client = await _get_client()
    if not query and status:
        query = f'ExecutionStatus = "{status}"'

    results: list[dict[str, Any]] = []
    cap = min(limit, 50)
    async for wf in client.list_workflows(query or ""):
        results.append(
            {
                "workflow_id": wf.id,
                "run_id": wf.run_id,
                "status": wf.status.name if wf.status else "UNKNOWN",
                "start_time": str(wf.start_time),
                "close_time": str(wf.close_time) if wf.close_time else None,
            }
        )
        if len(results) >= cap:
            break
    return {"count": len(results), "workflows": results}


@mcp.tool()
async def temporal_describe_workflow(
    workflow_id: str, run_id: str | None = None
) -> dict[str, Any]:
    """Get detailed state, execution status, pending activities, and history length.

    Args:
        workflow_id: The Temporal workflow ID (e.g. alert-incident-AM-20260724-5511ED).
        run_id: Optional run ID. Omit to use the most recent run.
    """
    client = await _get_client()
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    desc = await handle.describe()
    return {
        "workflow_id": desc.id,
        "run_id": desc.run_id,
        "status": desc.status.name,
        "start_time": str(desc.start_time),
        "close_time": str(desc.close_time) if desc.close_time else None,
        "history_length": desc.history_length,
        "memo": dict(desc.memo) if desc.memo else {},
    }


@mcp.tool()
async def temporal_signal_workflow(
    workflow_id: str,
    signal_name: str,
    arg: Any = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Send a signal to a running Temporal workflow execution.

    Args:
        workflow_id: Target workflow ID.
        signal_name: Signal name — e.g. alert.resolved, approve_fix, request_human.
        arg: Optional JSON-serializable argument to pass with the signal.
        run_id: Optional run ID.
    """
    client = await _get_client()
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    if arg is not None:
        await handle.signal(signal_name, arg)
    else:
        await handle.signal(signal_name)
    return {"action": "signaled", "workflow_id": workflow_id, "signal_name": signal_name}


@mcp.tool()
async def temporal_query_workflow(
    workflow_id: str,
    query_name: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Query a live running workflow's registered query handler.

    Args:
        workflow_id: Target workflow ID.
        query_name: Query handler name — e.g. status, hitl, current_state.
        run_id: Optional run ID.
    """
    client = await _get_client()
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    res = await handle.query(query_name)
    return {"workflow_id": workflow_id, "query_name": query_name, "result": res}


@mcp.tool()
async def temporal_terminate_workflow(
    workflow_id: str,
    reason: str = "Terminated via Temporal MCP",
    run_id: str | None = None,
) -> dict[str, Any]:
    """Terminate a running Temporal workflow execution.

    Args:
        workflow_id: Target workflow ID.
        reason: Human-readable termination reason stored in history.
        run_id: Optional run ID.
    """
    client = await _get_client()
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    await handle.terminate(reason=reason)
    return {"action": "terminated", "workflow_id": workflow_id, "reason": reason}


def main() -> None:
    global _target, _namespace
    parser = argparse.ArgumentParser(
        description="Official Temporal MCP Server — stdio (local) or SSE (remote/shared)"
    )
    parser.add_argument(
        "--target",
        default=_target,
        help="Temporal gRPC target (e.g. localhost:7233 or temporal-frontend.temporal.svc:7233)",
    )
    parser.add_argument(
        "--namespace",
        default=_namespace,
        help="Temporal namespace (default: default)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport: 'stdio' for local IDE clients, 'sse' for remote HTTP server (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind when transport=sse (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8095")),
        help="Port to listen on when transport=sse (default: 8095 or $MCP_PORT)",
    )

    args = parser.parse_args()
    _target = args.target
    _namespace = args.namespace

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
