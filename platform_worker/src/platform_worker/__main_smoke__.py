"""Smoke: Start AlertIncidentWorkflow + signal alert.resolved."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

from temporalio.client import Client

from platform_worker.workflows.alert_incident import AlertIncidentInput

TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "agent-platform")
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")


async def main() -> int:
    tracking_id = f"alert-{uuid.uuid4().hex[:10]}"
    client = await Client.connect(TEMPORAL_HOST, namespace=TEMPORAL_NAMESPACE)
    handle = await client.start_workflow(
        "AlertIncidentWorkflow",
        AlertIncidentInput(
            tracking_id=tracking_id,
            alert={
                "summary": "lab smoke high CPU",
                "priority": "P2",
                "category": "infra",
                "labels": {"team": "lab", "service": "smoke"},
            },
        ),
        id=f"alert-incident-{tracking_id}",
        task_queue=TASK_QUEUE,
    )
    print(f"started workflow_id={handle.id} tracking_id={tracking_id}")
    # Let triage/ticket/notify complete
    await asyncio.sleep(3)
    status = await handle.query("status")
    print(f"status_after_open={status}")
    await handle.signal("alert.resolved")
    result = await handle.result()
    print(f"result={result}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
