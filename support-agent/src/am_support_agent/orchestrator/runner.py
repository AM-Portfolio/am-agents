"""Execute planned A2A tasks via specialist adapters (no Temporal yet)."""

from __future__ import annotations

from typing import Any

from am_support_agent.adapters import BaseHttpAdapter
from am_support_agent.contracts.enums import TaskStatus
from am_support_agent.contracts.schemas import TaskResult
from am_support_agent.orchestrator import ExecutionPlan, Planner, PlannedTask
from am_support_agent.orchestrator.execution import ExecutionService
from am_support_agent.observability import Metrics
from am_support_agent.registry import AgentRegistry
from am_support_agent.stores import MemoryTaskRunStore


class PlanRunner:
    def __init__(
        self,
        registry: AgentRegistry,
        adapters: dict[str, BaseHttpAdapter],
        execution: ExecutionService | None = None,
    ) -> None:
        self.registry = registry
        self.adapters = adapters
        self.execution = execution or ExecutionService(
            adapters,
            MemoryTaskRunStore(),
            Metrics(),
        )
        self.planner = Planner(registry)

    async def run(
        self,
        *,
        correlation_id: str,
        tasks: list[PlannedTask],
    ) -> dict[str, Any]:
        plan = self.planner.plan(correlation_id=correlation_id, tasks=tasks)
        requests = self.planner.to_requests(plan)
        results: list[TaskResult] = []
        for req in requests:
            results.append(await self.execution.execute(req))

        failed = [r for r in results if r.status in (TaskStatus.FAILED, TaskStatus.TIMED_OUT)]
        status = TaskStatus.SUCCEEDED if not failed else TaskStatus.FAILED
        return {
            "correlation_id": correlation_id,
            "status": status.value,
            "task_queue": "support-agent-v2",
            "results": [r.model_dump() for r in results],
        }
