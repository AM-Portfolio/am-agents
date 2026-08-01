"""End-to-end Temporal smoke for AlertIncident lifecycle (fake capabilities)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_alert_incident_lifecycle_smoke(monkeypatch):
    pytest.importorskip("temporalio")
    monkeypatch.setenv("SUPPORT_AGENT_INCIDENT_PARITY", "true")
    monkeypatch.setenv("SUPPORT_AGENT_RUNTIME_MODE", "test")
    monkeypatch.setenv("SUPPORT_AGENT_CAPABILITY_PROVIDER", "fake")
    monkeypatch.setenv("TEMPORAL_TASK_QUEUE", "support-agent-v2")
    # Keep recovery timer short for time-skipping env.
    monkeypatch.setenv("SUPPORT_AGENT_RECOVERY_STABILITY_SECONDS", "1")

    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    from am_support_agent.orchestrator.activities.a2a import execute_plan
    from am_support_agent.orchestrator.activities.incident import INCIDENT_ACTIVITIES
    from am_support_agent.orchestrator.activities.telemetry import TELEMETRY_ACTIVITIES
    from am_support_agent.orchestrator.activities.spt import bootstrap_spt, resolve_spt_catalog
    from am_support_agent.orchestrator.workflows.alert_incident import AlertIncidentWorkflow
    from am_support_agent.orchestrator.workflows.a2a_run import SupportA2AWorkflow
    from am_support_agent.orchestrator.workflows.spt_run import SptRunWorkflow

    # Patch recovery sleep constant used by workflow module by monkeypatching timedelta usage
    # via a short wait — WorkflowEnvironment time-skipping advances timers automatically.
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="support-agent-v2",
            workflows=[SupportA2AWorkflow, AlertIncidentWorkflow, SptRunWorkflow],
            activities=[
                execute_plan,
                *INCIDENT_ACTIVITIES,
                *TELEMETRY_ACTIVITIES,
                bootstrap_spt,
                resolve_spt_catalog,
            ],
        ):
            handle = await env.client.start_workflow(
                AlertIncidentWorkflow.run,
                {
                    "tracking_id": "AM-SMOKE-1",
                    "alert": {
                        "service": "payments",
                        "env": "dev",
                        "status": "firing",
                        "fingerprint": "fp-smoke",
                        "title": "Smoke high error",
                    },
                },
                id="alert-incident-AM-SMOKE-1",
                task_queue="support-agent-v2",
            )

            # Wait until investigation path has notified (phase awaiting resolved).
            for _ in range(50):
                status = await handle.query(AlertIncidentWorkflow.status)
                if status.get("phase") in {
                    "awaiting_resolved_or_refired",
                    "verify_recovery",
                    "recovered",
                }:
                    break
                await env.sleep(1)

            status = await handle.query(AlertIncidentWorkflow.status)
            assert "retrieve_memory" in status.get("steps", {})
            assert "query_metrics" in status.get("steps", {}) or "observe_metrics" in status.get("steps", {})
            assert "intelligence_gate" in status.get("steps", {})
            assert "notify_firing" in status.get("steps", {})

            await handle.signal(AlertIncidentWorkflow.alert_resolved)
            result = await handle.result()
            assert result["status"] == "recovered"
            assert "close_ticket" in result["steps"]
            assert "notify_resolved" in result["steps"]
            assert "record_outcome_feedback" in result["steps"]
            assert "evaluate_learning" in result["steps"]
