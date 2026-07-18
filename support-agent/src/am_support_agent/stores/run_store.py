"""Support-agent task ledger.

SQLite is for local development, CI and shadow/parity runs. Production Postgres
compatibility with `libs/platform-adapters` is intentionally deferred — see
`docs/run-store.md`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from am_support_agent.contracts.enums import A2AOp, TaskStatus
from am_support_agent.contracts.schemas import TaskRequest, TaskResult


def _now() -> str:
    return datetime.now(UTC).isoformat()


class TaskRun(BaseModel):
    task_id: str
    correlation_id: str = ""
    agent_id: str
    capability: str = ""
    op: A2AOp
    status: TaskStatus
    idempotency_key: str | None = None
    request: dict
    result: dict | None = None
    feedback: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    updated_at: str


class TaskRunStore(Protocol):
    def create(self, request: TaskRequest) -> TaskRun: ...

    def complete(self, result: TaskResult) -> TaskRun: ...

    def cancel(
        self,
        task_id: str,
        *,
        agent_id: str,
        result: TaskResult,
        request: TaskRequest | None = None,
    ) -> TaskRun: ...

    def record_feedback(
        self,
        task_id: str,
        *,
        agent_id: str,
        result: TaskResult,
        request: TaskRequest | None = None,
    ) -> TaskRun: ...

    def get(self, task_id: str) -> TaskRun | None: ...

    def get_idempotent(
        self, agent_id: str, idempotency_key: str
    ) -> TaskResult | None: ...

    def ready(self) -> bool: ...


def _synthetic_request(
    task_id: str,
    *,
    agent_id: str,
    op: A2AOp,
    request: TaskRequest | None,
) -> dict:
    if request is not None:
        payload = request.model_dump(mode="json")
        payload["task_id"] = task_id
        return payload
    return {
        "task_id": task_id,
        "agent_id": agent_id,
        "op": op.value,
        "payload": {},
    }


class MemoryTaskRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, TaskRun] = {}
        self._idempotency: dict[tuple[str, str], str] = {}
        self._lock = threading.RLock()

    def create(self, request: TaskRequest) -> TaskRun:
        now = _now()
        with self._lock:
            if request.idempotency_key:
                key = (request.agent_id, request.idempotency_key)
                existing = self._idempotency.get(key)
                if existing:
                    return self._runs[existing]
            run = TaskRun(
                task_id=request.task_id,
                correlation_id=request.correlation_id,
                agent_id=request.agent_id,
                capability=request.capability,
                op=request.op,
                status=TaskStatus.ACCEPTED,
                idempotency_key=request.idempotency_key,
                request=request.model_dump(mode="json"),
                created_at=now,
                updated_at=now,
            )
            self._runs[run.task_id] = run
            if run.idempotency_key:
                self._idempotency[(run.agent_id, run.idempotency_key)] = run.task_id
            return run

    def complete(self, result: TaskResult) -> TaskRun:
        with self._lock:
            run = self._runs.get(result.task_id)
            if run is None:
                raise KeyError(f"unknown task_id: {result.task_id}")
            updated = run.model_copy(
                update={
                    "status": result.status,
                    "result": result.model_dump(mode="json"),
                    "updated_at": _now(),
                }
            )
            self._runs[result.task_id] = updated
            return updated

    def cancel(
        self,
        task_id: str,
        *,
        agent_id: str,
        result: TaskResult,
        request: TaskRequest | None = None,
    ) -> TaskRun:
        with self._lock:
            now = _now()
            existing = self._runs.get(task_id)
            if existing is None:
                run = TaskRun(
                    task_id=task_id,
                    correlation_id=request.correlation_id if request else "",
                    agent_id=agent_id,
                    capability=request.capability if request else "",
                    op=A2AOp.CANCEL,
                    status=TaskStatus.CANCELLED,
                    request=_synthetic_request(
                        task_id, agent_id=agent_id, op=A2AOp.CANCEL, request=request
                    ),
                    result=result.model_dump(mode="json"),
                    created_at=now,
                    updated_at=now,
                )
            else:
                run = existing.model_copy(
                    update={
                        "status": TaskStatus.CANCELLED,
                        "result": result.model_dump(mode="json"),
                        "updated_at": now,
                    }
                )
            self._runs[task_id] = run
            return run

    def record_feedback(
        self,
        task_id: str,
        *,
        agent_id: str,
        result: TaskResult,
        request: TaskRequest | None = None,
    ) -> TaskRun:
        with self._lock:
            now = _now()
            entry = {
                "recorded_at": now,
                "payload": request.payload if request else {},
                "result": result.model_dump(mode="json"),
            }
            existing = self._runs.get(task_id)
            if existing is None:
                run = TaskRun(
                    task_id=task_id,
                    correlation_id=request.correlation_id if request else "",
                    agent_id=agent_id,
                    capability=request.capability if request else "",
                    op=A2AOp.FEEDBACK,
                    status=result.status,
                    request=_synthetic_request(
                        task_id, agent_id=agent_id, op=A2AOp.FEEDBACK, request=request
                    ),
                    result=result.model_dump(mode="json"),
                    feedback=[entry],
                    created_at=now,
                    updated_at=now,
                )
            else:
                run = existing.model_copy(
                    update={
                        "feedback": [*existing.feedback, entry],
                        "updated_at": now,
                    }
                )
            self._runs[task_id] = run
            return run

    def get(self, task_id: str) -> TaskRun | None:
        with self._lock:
            return self._runs.get(task_id)

    def get_idempotent(
        self, agent_id: str, idempotency_key: str
    ) -> TaskResult | None:
        with self._lock:
            task_id = self._idempotency.get((agent_id, idempotency_key))
            run = self._runs.get(task_id) if task_id else None
            if not run or not run.result:
                return None
            return TaskResult.model_validate(run.result)

    def ready(self) -> bool:
        return True


class SqliteTaskRunStore:
    """Thread-safe SQLite ledger with durable idempotency."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS support_task_runs (
                    task_id TEXT PRIMARY KEY,
                    correlation_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    op TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    feedback_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cols = {
                row["name"]
                for row in self._conn.execute(
                    "PRAGMA table_info(support_task_runs)"
                ).fetchall()
            }
            if "feedback_json" not in cols:
                self._conn.execute(
                    "ALTER TABLE support_task_runs "
                    "ADD COLUMN feedback_json TEXT NOT NULL DEFAULT '[]'"
                )
            self._conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    support_task_runs_agent_idempotency
                ON support_task_runs(agent_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL
                """
            )

    def create(self, request: TaskRequest) -> TaskRun:
        now = _now()
        with self._lock, self._conn:
            if request.idempotency_key:
                existing = self._conn.execute(
                    """
                    SELECT * FROM support_task_runs
                    WHERE agent_id = ? AND idempotency_key = ?
                    """,
                    (request.agent_id, request.idempotency_key),
                ).fetchone()
                if existing:
                    return self._row(existing)
            self._conn.execute(
                """
                INSERT INTO support_task_runs (
                    task_id, correlation_id, agent_id, capability, op, status,
                    idempotency_key, request_json, result_json, feedback_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, '[]', ?, ?)
                """,
                (
                    request.task_id,
                    request.correlation_id,
                    request.agent_id,
                    request.capability,
                    request.op.value,
                    TaskStatus.ACCEPTED.value,
                    request.idempotency_key,
                    request.model_dump_json(),
                    now,
                    now,
                ),
            )
        run = self.get(request.task_id)
        if run is None:
            raise RuntimeError("failed to create task run")
        return run

    def complete(self, result: TaskResult) -> TaskRun:
        with self._lock, self._conn:
            changed = self._conn.execute(
                """
                UPDATE support_task_runs
                SET status = ?, result_json = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    result.status.value,
                    result.model_dump_json(),
                    _now(),
                    result.task_id,
                ),
            ).rowcount
            if changed != 1:
                raise KeyError(f"unknown task_id: {result.task_id}")
        run = self.get(result.task_id)
        if run is None:
            raise RuntimeError("failed to reload completed task run")
        return run

    def cancel(
        self,
        task_id: str,
        *,
        agent_id: str,
        result: TaskResult,
        request: TaskRequest | None = None,
    ) -> TaskRun:
        now = _now()
        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT * FROM support_task_runs WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if existing is None:
                self._conn.execute(
                    """
                    INSERT INTO support_task_runs (
                        task_id, correlation_id, agent_id, capability, op, status,
                        idempotency_key, request_json, result_json, feedback_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, '[]', ?, ?)
                    """,
                    (
                        task_id,
                        request.correlation_id if request else "",
                        agent_id,
                        request.capability if request else "",
                        A2AOp.CANCEL.value,
                        TaskStatus.CANCELLED.value,
                        json.dumps(
                            _synthetic_request(
                                task_id,
                                agent_id=agent_id,
                                op=A2AOp.CANCEL,
                                request=request,
                            )
                        ),
                        result.model_dump_json(),
                        now,
                        now,
                    ),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE support_task_runs
                    SET status = ?, result_json = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (
                        TaskStatus.CANCELLED.value,
                        result.model_dump_json(),
                        now,
                        task_id,
                    ),
                )
        run = self.get(task_id)
        if run is None:
            raise RuntimeError("failed to reload cancelled task run")
        return run

    def record_feedback(
        self,
        task_id: str,
        *,
        agent_id: str,
        result: TaskResult,
        request: TaskRequest | None = None,
    ) -> TaskRun:
        now = _now()
        entry = {
            "recorded_at": now,
            "payload": request.payload if request else {},
            "result": result.model_dump(mode="json"),
        }
        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT * FROM support_task_runs WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if existing is None:
                self._conn.execute(
                    """
                    INSERT INTO support_task_runs (
                        task_id, correlation_id, agent_id, capability, op, status,
                        idempotency_key, request_json, result_json, feedback_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        request.correlation_id if request else "",
                        agent_id,
                        request.capability if request else "",
                        A2AOp.FEEDBACK.value,
                        result.status.value,
                        json.dumps(
                            _synthetic_request(
                                task_id,
                                agent_id=agent_id,
                                op=A2AOp.FEEDBACK,
                                request=request,
                            )
                        ),
                        result.model_dump_json(),
                        json.dumps([entry]),
                        now,
                        now,
                    ),
                )
            else:
                prior = json.loads(existing["feedback_json"] or "[]")
                prior.append(entry)
                self._conn.execute(
                    """
                    UPDATE support_task_runs
                    SET feedback_json = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (json.dumps(prior), now, task_id),
                )
        run = self.get(task_id)
        if run is None:
            raise RuntimeError("failed to reload feedback task run")
        return run

    def get(self, task_id: str) -> TaskRun | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM support_task_runs WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._row(row) if row else None

    def get_idempotent(
        self, agent_id: str, idempotency_key: str
    ) -> TaskResult | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT result_json FROM support_task_runs
                WHERE agent_id = ? AND idempotency_key = ?
                """,
                (agent_id, idempotency_key),
            ).fetchone()
        if not row or not row["result_json"]:
            return None
        return TaskResult.model_validate_json(row["result_json"])

    def ready(self) -> bool:
        try:
            with self._lock:
                return self._conn.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _row(row: sqlite3.Row) -> TaskRun:
        keys = row.keys()
        feedback_raw = row["feedback_json"] if "feedback_json" in keys else "[]"
        return TaskRun(
            task_id=row["task_id"],
            correlation_id=row["correlation_id"],
            agent_id=row["agent_id"],
            capability=row["capability"],
            op=A2AOp(row["op"]),
            status=TaskStatus(row["status"]),
            idempotency_key=row["idempotency_key"],
            request=json.loads(row["request_json"]),
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            feedback=json.loads(feedback_raw or "[]"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
