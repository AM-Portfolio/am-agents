"""Thin Temporal client helpers for the gateway."""

from __future__ import annotations

import os
from typing import Any

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233").strip()
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default").strip()
TEMPORAL_TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "agent-platform").strip()


async def connect() -> Client:
    return await Client.connect(TEMPORAL_HOST, namespace=TEMPORAL_NAMESPACE)


async def start_alert_incident(
    *,
    workflow_id: str,
    tracking_id: str,
    alert: dict[str, Any],
    run_ref: str,
) -> dict[str, str]:
    client = await connect()
    args = {"tracking_id": tracking_id, "alert": alert, "run_ref": run_ref}
    try:
        handle = await client.start_workflow(
            "AlertIncidentWorkflow",
            args,
            id=workflow_id,
            task_queue=TEMPORAL_TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        return {"action": "started", "workflow_id": handle.id, "run_ref": run_ref}
    except WorkflowAlreadyStartedError:
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal("alert.refired")
        return {"action": "refired", "workflow_id": workflow_id, "run_ref": run_ref}


async def start_spt(
    *,
    workflow_id: str,
    demand: dict[str, Any],
    run_ref: str,
) -> dict[str, str]:
    client = await connect()
    args = {"demand": demand, "run_ref": run_ref}
    handle = await client.start_workflow(
        "SptRunWorkflow",
        args,
        id=workflow_id,
        task_queue=TEMPORAL_TASK_QUEUE,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )
    return {"action": "started", "workflow_id": handle.id, "run_ref": run_ref}


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
    }
