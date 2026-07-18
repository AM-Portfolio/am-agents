"""Full real-config AlertIncident lifecycle against live dev backends.

Runs the worker with the REAL capability provider (tool-agent), real Postgres
stores, real Grafana observe, real OpenProject work-items and real Zoho Cliq —
isolated on Temporal namespace `local` + queue `support-agent-v2-local-test`.

Env is supplied by the launcher (mirrors dev Vault config with local overrides).
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

from temporalio.client import Client
from temporalio.worker import Worker

from am_support_agent.orchestrator.activities.a2a import execute_plan
from am_support_agent.orchestrator.activities.incident import INCIDENT_ACTIVITIES
from am_support_agent.orchestrator.activities.spt import bootstrap_spt, resolve_spt_catalog
from am_support_agent.orchestrator.activities.telemetry import TELEMETRY_ACTIVITIES
from am_support_agent.orchestrator.workflows.a2a_run import SupportA2AWorkflow
from am_support_agent.orchestrator.workflows.alert_incident import AlertIncidentWorkflow
from am_support_agent.orchestrator.workflows.spt_run import SptRunWorkflow

TERMINAL_PHASES = {
    "not_confirmed",
    "inconclusive_closed",
    "human_handoff_complete",
    "recovered",
    "closed",
    "gated",
}


async def _drive(client: Client, handle, *, max_seconds: int = 240) -> dict:
    signaled_resolved = False
    deadline = asyncio.get_event_loop().time() + max_seconds
    last_phase = ""
    while asyncio.get_event_loop().time() < deadline:
        try:
            status = await handle.query(AlertIncidentWorkflow.status)
        except Exception as exc:  # workflow may have completed
            print(f"[query] {exc}")
            break
        phase = status.get("phase", "")
        if phase != last_phase:
            print(f"[phase] {phase}  steps={sorted(status.get('steps', {}).keys())}")
            last_phase = phase
        if phase == "awaiting_resolved_or_refired" and not signaled_resolved:
            print("[signal] sending alert.resolved to drive recovery verification")
            await handle.signal(AlertIncidentWorkflow.alert_resolved)
            signaled_resolved = True
        # Terminal workflow states end the run; result() returns below.
        desc = await handle.describe()
        if str(desc.status) not in ("WorkflowExecutionStatus.RUNNING", "1"):
            break
        await asyncio.sleep(3)
    return await handle.result()


async def main() -> None:
    host = os.environ["TEMPORAL_HOST"]
    namespace = os.environ["TEMPORAL_NAMESPACE"]
    task_queue = os.environ["TEMPORAL_TASK_QUEUE"]
    service = os.environ.get("E2E_SERVICE", "am-support-agent")
    env_name = os.environ.get("E2E_ENV", "dev")

    print(
        f"[boot] temporal={host} ns={namespace} queue={task_queue} "
        f"provider={os.environ.get('SUPPORT_AGENT_CAPABILITY_PROVIDER')} "
        f"tool_agent={os.environ.get('TOOL_AGENT_BASE_URL')}"
    )
    client = await Client.connect(host, namespace=namespace)

    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[SupportA2AWorkflow, AlertIncidentWorkflow, SptRunWorkflow],
        activities=[
            execute_plan,
            *INCIDENT_ACTIVITIES,
            *TELEMETRY_ACTIVITIES,
            bootstrap_spt,
            resolve_spt_catalog,
        ],
    ):
        suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        tracking_id = f"AM-LOCAL-E2E-{suffix}"
        alert = {
            "service": service,
            "env": env_name,
            "status": "firing",
            "severity": "warning",
            "fingerprint": f"local-e2e-{suffix}",
            "alertname": "LocalE2ERealConfig",
            "title": f"[LOCAL E2E TEST] {service} synthetic firing",
            "summary": "Isolated local end-to-end test against real dev backends. Safe to close.",
        }
        print(f"[start] {tracking_id} alert={alert['service']}/{alert['env']}")
        handle = await client.start_workflow(
            AlertIncidentWorkflow.run,
            {"tracking_id": tracking_id, "alert": alert, "run_ref": tracking_id},
            id=f"alert-incident-{tracking_id}",
            task_queue=task_queue,
        )
        result = await _drive(client, handle)

    print("\n===== FINAL RESULT =====")
    print(f"status : {result.get('status')}")
    print(f"phase  : {result.get('phase')}")
    print(f"work_item : {json.dumps(result.get('work_item'))}")
    print(f"owner  : {json.dumps(result.get('owner'))}")
    print(f"episode_id : {result.get('episode_id')}")
    steps = result.get("steps", {})
    print(f"steps executed ({len(steps)}): {sorted(steps.keys())}")
    for key in ("create_ticket", "assign_ticket", "notify_firing", "close_ticket", "notify_resolved"):
        s = steps.get(key)
        if isinstance(s, dict):
            print(f"  - {key}: ok={s.get('ok')} error={s.get('error')}")
    print("========================")


if __name__ == "__main__":
    asyncio.run(main())
