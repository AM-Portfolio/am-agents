"""Durable A2A execution service shared by gateway and plan runner."""

from __future__ import annotations

from am_support_agent.adapters import BaseHttpAdapter
from am_support_agent.contracts.enums import A2AOp, TaskStatus
from am_support_agent.contracts.schemas import TaskError, TaskRequest, TaskResult
from am_support_agent.observability import Metrics, finish_task_span, task_span
from am_support_agent.stores import TaskRunStore


class ExecutionService:
    def __init__(
        self,
        adapters: dict[str, BaseHttpAdapter],
        store: TaskRunStore,
        metrics: Metrics,
    ) -> None:
        self.adapters = adapters
        self.store = store
        self.metrics = metrics

    def _target_task_id(self, request: TaskRequest) -> str:
        raw = request.payload.get("target_task_id") or request.payload.get("task_id")
        if raw:
            return str(raw)
        return request.task_id

    async def execute(self, request: TaskRequest) -> TaskResult:
        self.metrics.task_started(request)
        with task_span(request) as span:
            try:
                result = await self._execute(request)
            except Exception:
                self.metrics.task_aborted(request)
                span.set_attribute("task.status", TaskStatus.FAILED.value)
                span.set_attribute("error.type", "unhandled")
                raise
            self.metrics.observe(request, result)
            finish_task_span(span, result)
            return result

    async def _execute(self, request: TaskRequest) -> TaskResult:
        if request.op == A2AOp.CANCEL:
            return await self._cancel(request)
        if request.op == A2AOp.FEEDBACK:
            return await self._feedback(request)

        if request.op == A2AOp.EXECUTE and request.idempotency_key:
            cached = self.store.get_idempotent(
                request.agent_id, request.idempotency_key
            )
            if cached is not None:
                self.metrics.idempotency_hit(request)
                return cached

        created = self.store.create(request)
        if created.task_id != request.task_id and created.result:
            self.metrics.idempotency_hit(request)
            return TaskResult.model_validate(created.result)

        adapter = self.adapters.get(request.agent_id)
        if adapter is None:
            result = TaskResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                agent_id=request.agent_id,
                error=TaskError(
                    code="no_adapter",
                    message=f"no adapter for {request.agent_id}",
                ),
            )
        else:
            result = await adapter.handle(request)

        self.store.complete(result)
        return result

    async def _cancel(self, request: TaskRequest) -> TaskResult:
        target_id = self._target_task_id(request)
        cancel_request = request.model_copy(update={"task_id": target_id})
        adapter = self.adapters.get(request.agent_id)
        if adapter is None:
            result = TaskResult(
                task_id=target_id,
                status=TaskStatus.CANCELLED,
                agent_id=request.agent_id,
                error=TaskError(
                    code="no_adapter",
                    message=f"no adapter for {request.agent_id}",
                ),
                data={"note": "cancelled without specialist adapter"},
            )
        else:
            result = await adapter.handle(cancel_request)
        self.store.cancel(
            target_id,
            agent_id=request.agent_id,
            result=result,
            request=cancel_request,
        )
        return result

    async def _feedback(self, request: TaskRequest) -> TaskResult:
        target_id = self._target_task_id(request)
        feedback_request = request.model_copy(update={"task_id": target_id})
        adapter = self.adapters.get(request.agent_id)
        if adapter is None:
            result = TaskResult(
                task_id=target_id,
                status=TaskStatus.SUCCEEDED,
                agent_id=request.agent_id,
                data={"stored": "platform_store_only"},
            )
        else:
            result = await adapter.handle(feedback_request)
        self.store.record_feedback(
            target_id,
            agent_id=request.agent_id,
            result=result,
            request=feedback_request,
        )
        return result

    def status(self, task_id: str) -> dict | None:
        run = self.store.get(task_id)
        return run.model_dump(mode="json") if run else None

    def ready(self) -> bool:
        healthy = self.store.ready()
        self.metrics.set_run_store_health(healthy)
        return healthy
