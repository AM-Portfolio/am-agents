"""Task ledger persistence and idempotency tests."""

from __future__ import annotations

import pytest

from am_support_agent.contracts.enums import A2AOp, TaskStatus
from am_support_agent.contracts.schemas import TaskRequest, TaskResult
from am_support_agent.observability import Metrics
from am_support_agent.orchestrator.execution import ExecutionService
from am_support_agent.stores import MemoryTaskRunStore, SqliteTaskRunStore, build_task_run_store


def _request(task_id: str = "t1") -> TaskRequest:
    return TaskRequest(
        task_id=task_id,
        correlation_id="c1",
        agent_id="tool-agent",
        capability="tools.execute",
        op=A2AOp.EXECUTE,
        idempotency_key="idem-1",
        payload={"tool": "grafana.query"},
    )


def _exercise(store) -> None:
    request = _request()
    created = store.create(request)
    assert created.status == TaskStatus.ACCEPTED
    assert store.get("t1") is not None

    result = TaskResult(
        task_id="t1",
        agent_id="tool-agent",
        status=TaskStatus.SUCCEEDED,
        data={"ok": True},
    )
    completed = store.complete(result)
    assert completed.status == TaskStatus.SUCCEEDED
    cached = store.get_idempotent("tool-agent", "idem-1")
    assert cached is not None
    assert cached.task_id == "t1"
    assert store.create(_request("t2")).task_id == "t1"
    assert store.ready()


def test_memory_store():
    _exercise(MemoryTaskRunStore())


def test_sqlite_store_persists(tmp_path):
    path = tmp_path / "runs.db"
    first = SqliteTaskRunStore(path)
    _exercise(first)
    first.close()

    second = SqliteTaskRunStore(path)
    cached = second.get_idempotent("tool-agent", "idem-1")
    assert cached is not None
    assert cached.task_id == "t1"
    second.close()


def test_cancel_and_feedback_when_missing():
    store = MemoryTaskRunStore()
    cancel_result = TaskResult(
        task_id="missing-cancel",
        agent_id="tool-agent",
        status=TaskStatus.CANCELLED,
    )
    cancelled = store.cancel(
        "missing-cancel",
        agent_id="tool-agent",
        result=cancel_result,
    )
    assert cancelled.status == TaskStatus.CANCELLED
    assert store.get("missing-cancel") is not None

    fb_result = TaskResult(
        task_id="missing-fb",
        agent_id="tool-agent",
        status=TaskStatus.SUCCEEDED,
        data={"stored": True},
    )
    recorded = store.record_feedback(
        "missing-fb",
        agent_id="tool-agent",
        result=fb_result,
        request=TaskRequest(
            task_id="missing-fb",
            agent_id="tool-agent",
            op=A2AOp.FEEDBACK,
            payload={"rating": "pass"},
        ),
    )
    assert len(recorded.feedback) == 1
    assert recorded.feedback[0]["payload"]["rating"] == "pass"


def test_feedback_preserves_existing_result(tmp_path):
    store = SqliteTaskRunStore(tmp_path / "fb.db")
    store.create(_request("keep-me"))
    store.complete(
        TaskResult(
            task_id="keep-me",
            agent_id="tool-agent",
            status=TaskStatus.SUCCEEDED,
            data={"ok": True},
        )
    )
    store.record_feedback(
        "keep-me",
        agent_id="tool-agent",
        result=TaskResult(
            task_id="keep-me",
            agent_id="tool-agent",
            status=TaskStatus.SUCCEEDED,
            data={"stored": "platform_adapter_memory"},
        ),
        request=TaskRequest(
            task_id="keep-me",
            agent_id="tool-agent",
            op=A2AOp.FEEDBACK,
            payload={"rating": "fail"},
        ),
    )
    run = store.get("keep-me")
    assert run is not None
    assert run.status == TaskStatus.SUCCEEDED
    assert run.result is not None
    assert run.result["data"]["ok"] is True
    assert len(run.feedback) == 1
    store.close()


@pytest.mark.asyncio
async def test_execution_cancel_feedback_missing_target():
    store = MemoryTaskRunStore()
    execution = ExecutionService({}, store, Metrics())

    cancelled = await execution.execute(
        TaskRequest(
            task_id="op-1",
            agent_id="ghost-agent",
            op=A2AOp.CANCEL,
            payload={"target_task_id": "never-seen"},
        )
    )
    assert cancelled.status == TaskStatus.CANCELLED
    assert store.get("never-seen") is not None

    fb = await execution.execute(
        TaskRequest(
            task_id="op-2",
            agent_id="ghost-agent",
            op=A2AOp.FEEDBACK,
            payload={"target_task_id": "never-seen", "rating": "pass"},
        )
    )
    assert fb.status == TaskStatus.SUCCEEDED
    run = store.get("never-seen")
    assert run is not None
    assert len(run.feedback) == 1


def test_postgres_backend_requires_dsn(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_RUNSTORE", "postgres")
    monkeypatch.delenv("SUPPORT_AGENT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="SUPPORT_AGENT_DATABASE_URL"):
        build_task_run_store()


def test_a2a_postgres_schema_is_not_legacy():
    from am_support_agent.stores.schema import (
        A2A_POSTGRES_TABLE,
        LEGACY_RUNSTORE_TABLES,
        SUPPORT_AGENT_SCHEMA_SQL,
    )

    assert A2A_POSTGRES_TABLE == "support_agent.task_runs"
    assert "agent_runs" not in SUPPORT_AGENT_SCHEMA_SQL
    assert "agent_run_steps" not in SUPPORT_AGENT_SCHEMA_SQL
    assert "support_agent.task_runs" in SUPPORT_AGENT_SCHEMA_SQL
    assert LEGACY_RUNSTORE_TABLES.isdisjoint({"support_agent.task_runs"})
