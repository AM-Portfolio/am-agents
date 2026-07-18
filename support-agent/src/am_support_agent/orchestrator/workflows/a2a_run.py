"""Support-agent A2A Temporal workflow (queue: support-agent-v2)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from am_support_agent.orchestrator.activities.a2a import execute_plan


@workflow.defn(name="SupportA2AWorkflow")
class SupportA2AWorkflow:
    """Parallel replacement workflow — does not replace AlertIncidentWorkflow."""

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            execute_plan,
            payload,
            start_to_close_timeout=timedelta(minutes=15),
        )
