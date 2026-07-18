"""Orchestrator — planner/router/runner. Temporal worker later on queue support-agent-v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from am_support_agent.contracts.enums import A2AOp, SupportDomain
from am_support_agent.contracts.schemas import TaskBudget, TaskRequest
from am_support_agent.orchestrator.router import Router
from am_support_agent.registry import AgentRegistry
from am_support_agent.runtime import new_task_id, validate_fanout

TEMPORAL_TASK_QUEUE = "support-agent-v2"


@dataclass
class PlannedTask:
    agent_id: str
    capability: str
    op: A2AOp
    business_domain: SupportDomain = SupportDomain.UNKNOWN
    requires_human: bool = False
    payload: dict[str, Any] = field(default_factory=dict)
    require_legacy_db: bool = False


@dataclass
class ExecutionPlan:
    correlation_id: str
    tasks: list[PlannedTask]
    budget: TaskBudget


class Planner:
    """Minimal DAG planner — expands to full planner module later."""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry
        self.router = Router(registry)

    def plan(
        self,
        *,
        correlation_id: str,
        tasks: list[PlannedTask],
        budget: TaskBudget | None = None,
    ) -> ExecutionPlan:
        b = budget or self.registry.default_budget
        validate_fanout(len(tasks), b)
        resolved: list[PlannedTask] = []
        for t in tasks:
            card = self.router.route(
                agent_id=t.agent_id or None,
                capability=t.capability,
                require_legacy_db=t.require_legacy_db,
            )
            resolved.append(
                PlannedTask(
                    agent_id=card.agent_id,
                    capability=t.capability,
                    op=t.op,
                    business_domain=t.business_domain,
                    requires_human=t.requires_human,
                    payload=t.payload,
                    require_legacy_db=t.require_legacy_db,
                )
            )
        return ExecutionPlan(correlation_id=correlation_id, tasks=resolved, budget=b)

    def to_requests(self, plan: ExecutionPlan) -> list[TaskRequest]:
        out: list[TaskRequest] = []
        for t in plan.tasks:
            out.append(
                TaskRequest(
                    task_id=new_task_id(),
                    correlation_id=plan.correlation_id,
                    agent_id=t.agent_id,
                    capability=t.capability,
                    op=t.op,
                    business_domain=t.business_domain,
                    requires_human=t.requires_human,
                    idempotency_key=new_task_id() if t.op == A2AOp.EXECUTE else None,
                    budget=plan.budget,
                    payload=t.payload,
                )
            )
        return out


def worker_main_help() -> str:
    return (
        f"Start with am-support-agent-worker on queue {TEMPORAL_TASK_QUEUE}. "
        f"Registers SupportA2AWorkflow, AlertIncidentWorkflow (gated), "
        f"SptRunWorkflow (gated). Legacy queue agent-platform remains owned "
        f"by platform_worker/."
    )


def __getattr__(name: str) -> Any:
    # Lazy: importing this package must stay sandbox-safe for Temporal workflows.
    if name == "PlanRunner":
        from am_support_agent.orchestrator.runner import PlanRunner

        return PlanRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "TEMPORAL_TASK_QUEUE",
    "PlannedTask",
    "ExecutionPlan",
    "Planner",
    "Router",
    "PlanRunner",
    "worker_main_help",
]
