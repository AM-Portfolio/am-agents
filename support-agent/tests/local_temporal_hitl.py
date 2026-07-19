"""Run the human-handoff flow against a local-only Temporal namespace and queue."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

os.environ.setdefault("SUPPORT_AGENT_INCIDENT_PARITY", "true")
os.environ.setdefault("SUPPORT_AGENT_RUNTIME_MODE", "test")
os.environ.setdefault("SUPPORT_AGENT_CAPABILITY_PROVIDER", "fake")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

from am_support_agent.orchestrator.activities.a2a import execute_plan
from am_support_agent.orchestrator.activities.incident import (
    INCIDENT_ACTIVITIES,
    query_metrics,
)
from am_support_agent.orchestrator.activities.spt import bootstrap_spt, resolve_spt_catalog
from am_support_agent.orchestrator.workflows.a2a_run import SupportA2AWorkflow
from am_support_agent.orchestrator.workflows.alert_incident import AlertIncidentWorkflow
from am_support_agent.orchestrator.workflows.spt_run import SptRunWorkflow


@activity.defn(name="support_agent.incident.query_metrics")
async def query_metrics_hitl_test(payload: dict) -> dict:
    """Force missing metrics evidence while retaining fake ticket capabilities."""
    tracking_id = str(payload.get("tracking_id") or "")
    return {
        "gated": False,
        "phase": "query_metrics",
        "tracking_id": tracking_id,
        "observation": {
            "kind": "metrics",
            "transport_ok": False,
            "parseable": False,
            "healthy": False,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "summary": "local test: metrics transport unavailable",
            "query_ref": "local_hitl_test",
            "data": {},
            "predicates": [],
        },
    }


async def main() -> None:
    host = os.getenv("TEMPORAL_HOST", "localhost:17233")
    namespace = os.getenv("TEMPORAL_NAMESPACE", "local")
    task_queue = os.getenv("TEMPORAL_TASK_QUEUE", "support-agent-v2-local-test")
    client = await Client.connect(host, namespace=namespace)
    activities = [
        query_metrics_hitl_test if fn is query_metrics else fn
        for fn in INCIDENT_ACTIVITIES
    ]

    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[SupportA2AWorkflow, AlertIncidentWorkflow, SptRunWorkflow],
        activities=[
            execute_plan,
            *activities,
            bootstrap_spt,
            resolve_spt_catalog,
        ],
    ):
        suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        tracking_id = f"AM-LOCAL-HITL-{suffix}"
        handle = await client.start_workflow(
            AlertIncidentWorkflow.run,
            {
                "tracking_id": tracking_id,
                "alert": {
                    "service": "local-test-service",
                    "env": "local",
                    "status": "firing",
                    "fingerprint": f"local-hitl-{suffix}",
                    "title": "Local human handoff test",
                },
            },
            id=f"alert-incident-{tracking_id}",
            task_queue=task_queue,
        )
        result = await handle.result()
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") != "human_required":
            raise RuntimeError(f"expected human_required, got {result.get('status')}")
        if not result.get("work_item"):
            raise RuntimeError("human handoff did not create/assign a work item")


if __name__ == "__main__":
    asyncio.run(main())
