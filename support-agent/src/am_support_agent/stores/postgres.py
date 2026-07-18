"""Postgres A2A TaskRunStore — dedicated support_agent schema only.

Requires optional extra: pip install 'am-support-agent[postgres]'
Env: SUPPORT_AGENT_DATABASE_URL (or DATABASE_URL)
"""

from __future__ import annotations

import json
import threading
from typing import Any

from am_support_agent.contracts.enums import A2AOp, TaskStatus
from am_support_agent.contracts.schemas import TaskRequest, TaskResult
from am_support_agent.stores.run_store import TaskRun, _now, _synthetic_request
from am_support_agent.stores.schema import SUPPORT_AGENT_SCHEMA_SQL


class PostgresTaskRunStore:
    """Thread-safe A2A ledger on support_agent.task_runs (not agent_runs)."""

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "SUPPORT_AGENT_RUNSTORE=postgres requires psycopg. "
                "Install with: pip install 'am-support-agent[postgres]'"
            ) from exc
        self._psycopg = psycopg
        self._dsn = dsn
        self._lock = threading.RLock()
        self._conn = psycopg.connect(dsn, row_factory=dict_row)
        self._conn.autocommit = False
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(SUPPORT_AGENT_SCHEMA_SQL)
            self._conn.commit()

    def create(self, request: TaskRequest) -> TaskRun:
        now = _now()
        with self._lock:
            with self._conn.cursor() as cur:
                if request.idempotency_key:
                    cur.execute(
                        """
                        SELECT * FROM support_agent.task_runs
                        WHERE agent_id = %s AND idempotency_key = %s
                        """,
                        (request.agent_id, request.idempotency_key),
                    )
                    existing = cur.fetchone()
                    if existing:
                        self._conn.commit()
                        return self._row(existing)
                cur.execute(
                    """
                    INSERT INTO support_agent.task_runs (
                        task_id, correlation_id, agent_id, capability, op, status,
                        idempotency_key, request_json, result_json, feedback_json,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, '[]', %s, %s)
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
            self._conn.commit()
        run = self.get(request.task_id)
        if run is None:
            raise RuntimeError("failed to create task run")
        return run

    def complete(self, result: TaskResult) -> TaskRun:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE support_agent.task_runs
                    SET status = %s, result_json = %s, updated_at = %s
                    WHERE task_id = %s
                    """,
                    (
                        result.status.value,
                        result.model_dump_json(),
                        _now(),
                        result.task_id,
                    ),
                )
                if cur.rowcount == 0:
                    self._conn.rollback()
                    raise KeyError(f"unknown task_id: {result.task_id}")
            self._conn.commit()
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
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM support_agent.task_runs WHERE task_id = %s",
                    (task_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    cur.execute(
                        """
                        INSERT INTO support_agent.task_runs (
                            task_id, correlation_id, agent_id, capability, op, status,
                            idempotency_key, request_json, result_json, feedback_json,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s, '[]', %s, %s)
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
                    cur.execute(
                        """
                        UPDATE support_agent.task_runs
                        SET status = %s, result_json = %s, updated_at = %s
                        WHERE task_id = %s
                        """,
                        (
                            TaskStatus.CANCELLED.value,
                            result.model_dump_json(),
                            now,
                            task_id,
                        ),
                    )
            self._conn.commit()
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
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM support_agent.task_runs WHERE task_id = %s",
                    (task_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    cur.execute(
                        """
                        INSERT INTO support_agent.task_runs (
                            task_id, correlation_id, agent_id, capability, op, status,
                            idempotency_key, request_json, result_json, feedback_json,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s)
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
                    cur.execute(
                        """
                        UPDATE support_agent.task_runs
                        SET feedback_json = %s, updated_at = %s
                        WHERE task_id = %s
                        """,
                        (json.dumps(prior), now, task_id),
                    )
            self._conn.commit()
        run = self.get(task_id)
        if run is None:
            raise RuntimeError("failed to reload feedback task run")
        return run

    def get(self, task_id: str) -> TaskRun | None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM support_agent.task_runs WHERE task_id = %s",
                    (task_id,),
                )
                row = cur.fetchone()
            self._conn.commit()
        return self._row(row) if row else None

    def get_idempotent(
        self, agent_id: str, idempotency_key: str
    ) -> TaskResult | None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT result_json FROM support_agent.task_runs
                    WHERE agent_id = %s AND idempotency_key = %s
                    """,
                    (agent_id, idempotency_key),
                )
                row = cur.fetchone()
            self._conn.commit()
        if not row or not row["result_json"]:
            return None
        return TaskResult.model_validate_json(row["result_json"])

    def ready(self) -> bool:
        try:
            with self._lock:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    ok = cur.fetchone() is not None
                self._conn.commit()
                return ok
        except Exception:  # noqa: BLE001
            return False

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _row(row: dict[str, Any]) -> TaskRun:
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
            feedback=json.loads(row.get("feedback_json") or "[]"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
