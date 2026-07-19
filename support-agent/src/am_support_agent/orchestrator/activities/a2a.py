"""A2A plan execution activity — calls specialist adapters only."""

from __future__ import annotations

from typing import Any

from temporalio import activity

from am_support_agent.adapters import build_adapters
from am_support_agent.contracts.enums import A2AOp, SupportDomain
from am_support_agent.orchestrator import PlanRunner, PlannedTask
from am_support_agent.registry import get_registry


@activity.defn(name="support_agent.execute_plan")
async def execute_plan(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a support-agent plan against live specialist HTTP APIs."""
    registry = get_registry()
    adapters = build_adapters(registry.list_cards())
    runner = PlanRunner(registry, adapters)
    tasks_raw = list(payload.get("tasks") or [])
    tasks: list[PlannedTask] = []
    for t in tasks_raw:
        op_raw = t.get("op", "execute")
        op = A2AOp(op_raw) if not isinstance(op_raw, A2AOp) else op_raw
        tasks.append(
            PlannedTask(
                agent_id=str(t.get("agent_id") or ""),
                capability=str(t.get("capability") or ""),
                op=op,
                business_domain=SupportDomain(
                    str(t.get("business_domain") or SupportDomain.UNKNOWN.value)
                ),
                requires_human=bool(t.get("requires_human")),
                payload=dict(t.get("payload") or {}),
                require_legacy_db=bool(t.get("require_legacy_db")),
            )
        )
    return await runner.run(
        correlation_id=str(payload.get("correlation_id") or ""),
        tasks=tasks,
    )
