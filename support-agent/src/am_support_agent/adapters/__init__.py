"""Specialist agent HTTP adapters."""

from __future__ import annotations

import time
from typing import Any, Protocol

import httpx

from am_support_agent.contracts.enums import A2AOp, TaskStatus
from am_support_agent.contracts.schemas import (
    AgentCard,
    EvidenceItem,
    TaskError,
    TaskMetrics,
    TaskRequest,
    TaskResult,
)
from am_support_agent.observability.tracing import (
    finish_task_span,
    inject_trace_headers,
    specialist_span,
)


class AgentAdapter(Protocol):
    agent_id: str

    async def handle(self, request: TaskRequest) -> TaskResult: ...


class BaseHttpAdapter:
    agent_id: str

    def __init__(
        self,
        card: AgentCard,
        client: httpx.AsyncClient | None = None,
        *,
        caller_header_value: str | None = None,
    ) -> None:
        self.card = card
        self.agent_id = card.agent_id
        self._client = client
        self._owns_client = client is None
        self._caller_header_value = caller_header_value
        self._last_by_task: dict[str, dict[str, Any]] = {}
        self._cancelled: set[str] = set()
        self._feedback: list[dict[str, Any]] = []

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.card.auth.header and self._caller_header_value:
            headers[self.card.auth.header] = self._caller_header_value
        inject_trace_headers(headers)
        return headers

    def _result(
        self,
        request: TaskRequest,
        *,
        status: TaskStatus,
        data: dict[str, Any] | None = None,
        evidence: list[EvidenceItem] | None = None,
        error: TaskError | None = None,
        latency_ms: int = 0,
    ) -> TaskResult:
        return TaskResult(
            task_id=request.task_id,
            status=status,
            agent_id=self.agent_id,
            evidence=evidence or [],
            error=error,
            metrics=TaskMetrics(latency_ms=latency_ms),
            data=data or {},
        )

    async def handle(self, request: TaskRequest) -> TaskResult:
        with specialist_span(request) as span:
            result = await self._handle(request)
            finish_task_span(span, result)
            return result

    async def _handle(self, request: TaskRequest) -> TaskResult:
        if request.agent_id != self.agent_id:
            return self._result(
                request,
                status=TaskStatus.FAILED,
                error=TaskError(
                    code="agent_mismatch",
                    message=f"adapter {self.agent_id} got agent_id={request.agent_id}",
                ),
            )
        if (
            request.task_id in self._cancelled
            and request.op not in (A2AOp.CANCEL, A2AOp.FEEDBACK, A2AOp.STATUS)
        ):
            return self._result(request, status=TaskStatus.CANCELLED)

        started = time.perf_counter()
        try:
            if request.op == A2AOp.DISCOVER:
                out = await self.discover(request)
            elif request.op == A2AOp.PLAN:
                out = await self.plan(request)
            elif request.op == A2AOp.EXECUTE:
                if not request.idempotency_key:
                    return self._result(
                        request,
                        status=TaskStatus.FAILED,
                        error=TaskError(
                            code="idempotency_required",
                            message="idempotency_key required for execute",
                        ),
                    )
                out = await self.execute(request)
            elif request.op == A2AOp.STATUS:
                out = await self.status(request)
            elif request.op == A2AOp.CANCEL:
                out = await self.cancel(request)
            elif request.op == A2AOp.FEEDBACK:
                out = await self.feedback(request)
            elif request.op == A2AOp.STREAM:
                out = await self.stream_snapshot(request)
            else:
                out = self._result(
                    request,
                    status=TaskStatus.FAILED,
                    error=TaskError(code="unsupported_op", message=str(request.op)),
                )
        except httpx.TimeoutException as exc:
            return self._result(
                request,
                status=TaskStatus.TIMED_OUT,
                error=TaskError(code="timeout", message=str(exc)[:200], retryable=True),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except httpx.HTTPError as exc:
            return self._result(
                request,
                status=TaskStatus.FAILED,
                error=TaskError(code="http_error", message=str(exc)[:200], retryable=True),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 — surface as task failure
            return self._result(
                request,
                status=TaskStatus.FAILED,
                error=TaskError(code="adapter_error", message=str(exc)[:200]),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        latency = int((time.perf_counter() - started) * 1000)
        out.metrics.latency_ms = latency
        return out

    async def discover(self, request: TaskRequest) -> TaskResult:
        client = await self._http()
        resp = await client.get(
            f"{self.card.base_url}{self.card.health.path}",
            headers=self._headers(),
        )
        body: dict[str, Any]
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            body = {"raw": resp.text[:500]}
        ok = resp.status_code < 400
        return self._result(
            request,
            status=TaskStatus.SUCCEEDED if ok else TaskStatus.FAILED,
            data={
                "agent_card": self.card.model_dump(),
                "health": body,
                "http_status": resp.status_code,
            },
            error=None
            if ok
            else TaskError(code="unhealthy", message=f"HTTP {resp.status_code}"),
        )

    async def plan(self, request: TaskRequest) -> TaskResult:
        raise NotImplementedError

    async def execute(self, request: TaskRequest) -> TaskResult:
        raise NotImplementedError

    async def status(self, request: TaskRequest) -> TaskResult:
        cached = self._last_by_task.get(request.task_id)
        if not cached:
            return self._result(
                request,
                status=TaskStatus.FAILED,
                error=TaskError(
                    code="unknown_task",
                    message="no correlated specialist status (adapter-synthesized)",
                ),
            )
        return self._result(
            request,
            status=TaskStatus(cached.get("status", TaskStatus.RUNNING.value)),
            data=cached,
        )

    async def cancel(self, request: TaskRequest) -> TaskResult:
        self._cancelled.add(request.task_id)
        return self._result(
            request,
            status=TaskStatus.CANCELLED,
            data={"note": "platform-task cancel only; specialist has no native cancel"},
        )

    async def feedback(self, request: TaskRequest) -> TaskResult:
        self._feedback.append({"task_id": request.task_id, "payload": request.payload})
        return self._result(
            request,
            status=TaskStatus.SUCCEEDED,
            data={"stored": "platform_adapter_memory", "count": len(self._feedback)},
        )

    async def stream_snapshot(self, request: TaskRequest) -> TaskResult:
        """Non-SSE snapshot used until gateway streams are wired."""
        st = await self.status(request)
        st.data = {**st.data, "stream": "snapshot"}
        return st


class ToolAgentAdapter(BaseHttpAdapter):
    async def plan(self, request: TaskRequest) -> TaskResult:
        client = await self._http()
        resp = await client.post(
            f"{self.card.base_url}/api/v1/tools/plan",
            headers=self._headers(),
            json=request.payload,
        )
        data = _json_or_text(resp)
        status = TaskStatus.SUCCEEDED if resp.status_code < 400 else TaskStatus.FAILED
        self._last_by_task[request.task_id] = {"status": status.value, "data": data}
        return self._result(
            request,
            status=status,
            data=data if isinstance(data, dict) else {"body": data},
            error=None
            if status == TaskStatus.SUCCEEDED
            else TaskError(code="plan_failed", message=f"HTTP {resp.status_code}"),
        )

    async def execute(self, request: TaskRequest) -> TaskResult:
        client = await self._http()
        headers = self._headers()
        headers["Idempotency-Key"] = request.idempotency_key or request.task_id
        resp = await client.post(
            f"{self.card.base_url}/api/v1/tools/execute",
            headers=headers,
            json=request.payload,
        )
        data = _json_or_text(resp)
        status = TaskStatus.SUCCEEDED if resp.status_code < 400 else TaskStatus.FAILED
        evidence = [
            EvidenceItem(
                kind="tool_execute",
                ref=str((data or {}).get("run_id") or request.task_id)
                if isinstance(data, dict)
                else request.task_id,
                provenance="tool-agent",
            )
        ]
        self._last_by_task[request.task_id] = {"status": status.value, "data": data}
        return self._result(
            request,
            status=status,
            data=data if isinstance(data, dict) else {"body": data},
            evidence=evidence,
            error=None
            if status == TaskStatus.SUCCEEDED
            else TaskError(code="execute_failed", message=f"HTTP {resp.status_code}"),
        )


class DbAgentAdapter(BaseHttpAdapter):
    async def plan(self, request: TaskRequest) -> TaskResult:
        client = await self._http()
        resp = await client.post(
            f"{self.card.base_url}/api/v1/db/plan",
            headers=self._headers(),
            json=request.payload,
        )
        data = _json_or_text(resp)
        status = TaskStatus.SUCCEEDED if resp.status_code < 400 else TaskStatus.FAILED
        self._last_by_task[request.task_id] = {"status": status.value, "data": data}
        return self._result(
            request,
            status=status,
            data=data if isinstance(data, dict) else {"body": data},
            error=None
            if status == TaskStatus.SUCCEEDED
            else TaskError(code="plan_failed", message=f"HTTP {resp.status_code}"),
        )

    async def execute(self, request: TaskRequest) -> TaskResult:
        client = await self._http()
        headers = self._headers()
        headers["Idempotency-Key"] = request.idempotency_key or request.task_id
        resp = await client.post(
            f"{self.card.base_url}/api/v1/db/execute",
            headers=headers,
            json=request.payload,
        )
        data = _json_or_text(resp)
        status = TaskStatus.SUCCEEDED if resp.status_code < 400 else TaskStatus.FAILED
        self._last_by_task[request.task_id] = {"status": status.value, "data": data}
        return self._result(
            request,
            status=status,
            data=data if isinstance(data, dict) else {"body": data},
            evidence=[
                EvidenceItem(
                    kind="db_execute",
                    ref=request.task_id,
                    provenance="db-agent",
                )
            ],
            error=None
            if status == TaskStatus.SUCCEEDED
            else TaskError(code="execute_failed", message=f"HTTP {resp.status_code}"),
        )


class UiTestAgentAdapter(BaseHttpAdapter):
    async def plan(self, request: TaskRequest) -> TaskResult:
        # Specialist has no /plan — synthesize from payload.
        steps = [
            {"step": 1, "action": "validate_request", "payload_keys": sorted(request.payload)},
            {"step": 2, "action": "POST /api/v1/test/run"},
            {"step": 3, "action": "poll /api/v1/test/status/{testId}"},
        ]
        data = {"synthesized": True, "steps": steps}
        self._last_by_task[request.task_id] = {
            "status": TaskStatus.SUCCEEDED.value,
            "data": data,
        }
        return self._result(request, status=TaskStatus.SUCCEEDED, data=data)

    async def execute(self, request: TaskRequest) -> TaskResult:
        client = await self._http()
        path = "/api/v1/test/run/auth" if request.payload.get("auth") else "/api/v1/test/run"
        resp = await client.post(
            f"{self.card.base_url}{path}",
            headers=self._headers(),
            json=request.payload,
        )
        data = _json_or_text(resp)
        if resp.status_code >= 400:
            return self._result(
                request,
                status=TaskStatus.FAILED,
                data=data if isinstance(data, dict) else {"body": data},
                error=TaskError(code="execute_failed", message=f"HTTP {resp.status_code}"),
            )
        test_id = ""
        if isinstance(data, dict):
            test_id = str(data.get("testId") or data.get("test_id") or "")
        self._last_by_task[request.task_id] = {
            "status": TaskStatus.RUNNING.value,
            "test_id": test_id,
            "data": data,
            "multi_replica_safe": self.card.limits.multi_replica_status,
        }
        return self._result(
            request,
            status=TaskStatus.RUNNING if test_id else TaskStatus.SUCCEEDED,
            data=data if isinstance(data, dict) else {"body": data},
            evidence=[
                EvidenceItem(
                    kind="ui_test_run",
                    ref=test_id or request.task_id,
                    provenance="ui-test-agent",
                )
            ],
        )

    async def status(self, request: TaskRequest) -> TaskResult:
        cached = self._last_by_task.get(request.task_id) or {}
        test_id = str(
            request.payload.get("test_id")
            or request.payload.get("testId")
            or cached.get("test_id")
            or ""
        )
        if not test_id:
            return await super().status(request)
        client = await self._http()
        resp = await client.get(
            f"{self.card.base_url}/api/v1/test/status/{test_id}",
            headers=self._headers(),
        )
        data = _json_or_text(resp)
        if resp.status_code >= 400:
            return self._result(
                request,
                status=TaskStatus.FAILED,
                data={"note": "ui status is process-local / non-HA", "body": data},
                error=TaskError(code="status_failed", message=f"HTTP {resp.status_code}"),
            )
        specialist_status = ""
        if isinstance(data, dict):
            specialist_status = str(data.get("status") or "").lower()
        mapped = TaskStatus.RUNNING
        if specialist_status in {"done", "completed", "succeeded", "success", "passed"}:
            mapped = TaskStatus.SUCCEEDED
        elif specialist_status in {"failed", "error"}:
            mapped = TaskStatus.FAILED
        self._last_by_task[request.task_id] = {
            "status": mapped.value,
            "test_id": test_id,
            "data": data,
            "multi_replica_safe": False,
        }
        return self._result(
            request,
            status=mapped,
            data=data if isinstance(data, dict) else {"body": data},
        )


def _json_or_text(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return resp.text[:1000]


def build_adapters(
    cards: list[AgentCard],
    *,
    client: httpx.AsyncClient | None = None,
    db_caller: str | None = None,
) -> dict[str, BaseHttpAdapter]:
    out: dict[str, BaseHttpAdapter] = {}
    for card in cards:
        if card.agent_id == "tool-agent":
            out[card.agent_id] = ToolAgentAdapter(card, client=client)
        elif card.agent_id == "db-agent":
            out[card.agent_id] = DbAgentAdapter(
                card,
                client=client,
                caller_header_value=db_caller or "am-support-agent",
            )
        elif card.agent_id == "ui-test-agent":
            out[card.agent_id] = UiTestAgentAdapter(card, client=client)
        else:
            out[card.agent_id] = BaseHttpAdapter(card, client=client)
    return out


# Storage / LLM boundaries (composition root later)
from am_support_agent.adapters.llm import (  # noqa: E402
    complete_gated,
    llm_enabled,
    llm_status,
)
from am_support_agent.adapters.storage import (  # noqa: E402
    DEFAULT_DOC_PREFIX,
    DocStoreNamespace,
    legacy_postgres_runstore_compatible,
)
