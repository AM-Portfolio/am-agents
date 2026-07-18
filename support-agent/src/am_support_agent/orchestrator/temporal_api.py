"""Temporal client helpers for support-agent gateway (queue support-agent-v2)."""

from __future__ import annotations

import os
from typing import Any

from am_support_agent.observability import temporal_interceptors
from am_support_agent.orchestrator import TEMPORAL_TASK_QUEUE as DEFAULT_QUEUE


def _host() -> str:
    return os.getenv("TEMPORAL_HOST", "localhost:7233")


def _namespace() -> str:
    return os.getenv("TEMPORAL_NAMESPACE", "default")


def _task_queue() -> str:
    queue = os.getenv("TEMPORAL_TASK_QUEUE", DEFAULT_QUEUE)
    if queue == "agent-platform":
        raise ValueError("Refusing legacy Temporal queue agent-platform")
    return queue


def temporal_enabled() -> bool:
    return os.getenv("SUPPORT_AGENT_TEMPORAL_ENABLED", "").lower() in {
        "1",
        "true",
        "yes",
    }


async def connect():
    from temporalio.client import Client

    return await Client.connect(
        _host(),
        namespace=_namespace(),
        interceptors=temporal_interceptors(),
    )


async def start_alert_incident(
    *,
    workflow_id: str,
    tracking_id: str,
    alert: dict[str, Any],
    run_ref: str,
) -> dict[str, str]:
    from temporalio.common import WorkflowIDReusePolicy
    from temporalio.exceptions import WorkflowAlreadyStartedError

    client = await connect()
    args = {"tracking_id": tracking_id, "alert": alert, "run_ref": run_ref}
    try:
        handle = await client.start_workflow(
            "AlertIncidentWorkflow",
            args,
            id=workflow_id,
            task_queue=_task_queue(),
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        return {
            "action": "started",
            "workflow_id": handle.id,
            "run_ref": run_ref,
            "task_queue": _task_queue(),
        }
    except WorkflowAlreadyStartedError:
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal("alert.refired")
        return {
            "action": "refired",
            "workflow_id": workflow_id,
            "run_ref": run_ref,
            "task_queue": _task_queue(),
        }


async def start_spt(
    *,
    workflow_id: str,
    demand: dict[str, Any],
    run_ref: str,
) -> dict[str, str]:
    from temporalio.common import WorkflowIDReusePolicy

    client = await connect()
    args = {"demand": demand, "run_ref": run_ref}
    handle = await client.start_workflow(
        "SptRunWorkflow",
        args,
        id=workflow_id,
        task_queue=_task_queue(),
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )
    return {
        "action": "started",
        "workflow_id": handle.id,
        "run_ref": run_ref,
        "task_queue": _task_queue(),
    }


async def signal_workflow(*, workflow_id: str, signal_name: str) -> dict[str, str]:
    client = await connect()
    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(signal_name)
    return {"action": "signaled", "workflow_id": workflow_id, "signal": signal_name}


async def query_status(*, workflow_id: str) -> dict[str, Any]:
    client = await connect()
    handle = client.get_workflow_handle(workflow_id)
    status = await handle.query("status")
    desc = await handle.describe()
    return {
        "workflow_id": workflow_id,
        "temporal_status": str(desc.status),
        "query": status if isinstance(status, dict) else {"value": status},
        "task_queue": _task_queue(),
    }


__all__ = [
    "temporal_enabled",
    "connect",
    "start_alert_incident",
    "start_spt",
    "signal_workflow",
    "query_status",
]
