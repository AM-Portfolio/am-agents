"""Support-agent A2A Temporal workflow (queue: support-agent-v2)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

# Activity is referenced by registered name so this module never imports
# adapters/httpx (sandbox-restricted) during workflow validation.
_EXECUTE_PLAN = "support_agent.execute_plan"


@workflow.defn(name="SupportA2AWorkflow")
class SupportA2AWorkflow:
    """Parallel replacement workflow — does not replace AlertIncidentWorkflow."""

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            _EXECUTE_PLAN,
            payload,
            start_to_close_timeout=timedelta(minutes=15),
        )
