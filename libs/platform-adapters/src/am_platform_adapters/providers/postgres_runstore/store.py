"""Postgres RunStore — agent_runs / agent_run_steps (ADR-005)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from am_platform_ports.schemas.enums import ErrorClass, RunKind, RunStatus, StepStatus
from am_platform_ports.schemas.run import AgentRun, AgentRunStep, CreateRunRequest, UpsertStepRequest


def _now() -> datetime:
    return datetime.now(UTC)


def _ref(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _connect(dsn: str | None = None):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "psycopg required for RUN_STORE_PROVIDER=postgres — pip install 'psycopg[binary]'"
        ) from exc
    url = (dsn or os.environ.get("RUN_STORE_DSN") or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("RUN_STORE_DSN (or DATABASE_URL) is required for postgres RunStore")
    return psycopg.connect(url, row_factory=dict_row, autocommit=False)


def _row_run(row: dict[str, Any]) -> AgentRun:
    summary = row.get("summary_json") or {}
    if isinstance(summary, str):
        summary = json.loads(summary)
    return AgentRun(
        run_ref=row["run_ref"],
        kind=RunKind(row["kind"]),
        status=RunStatus(row["status"]),
        parent_run_ref=row.get("parent_run_ref"),
        incident_ref=row.get("incident_ref"),
        ticket_ref=row.get("ticket_ref"),
        demand_ref=row.get("demand_ref"),
        workflow_id=row.get("workflow_id"),
        requested_selector_hash=row.get("requested_selector_hash"),
        summary=dict(summary),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _row_step(row: dict[str, Any]) -> AgentRunStep:
    err = row.get("last_error_class")
    return AgentRunStep(
        step_ref=row["step_ref"],
        run_ref=row["run_ref"],
        name=row["name"],
        check_ref=row.get("check_ref"),
        status=StepStatus(row["status"]),
        claim_lease_until=row.get("claim_lease_until"),
        worker_id=row.get("worker_id"),
        attempts=int(row.get("attempts") or 0),
        last_error_class=ErrorClass(err) if err else None,
        result_ref=row.get("result_ref"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


class PostgresRunStore:
    """Durable RunStore with SKIP LOCKED claim semantics."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn

    def create_run(self, request: CreateRunRequest) -> AgentRun:
        run_ref = _ref("run")
        now = _now()
        with _connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_runs (
                        run_ref, kind, status, parent_run_ref, incident_ref, ticket_ref,
                        demand_ref, workflow_id, requested_selector_hash, summary_json,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb, %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        run_ref,
                        request.kind.value,
                        request.status.value,
                        request.parent_run_ref,
                        request.incident_ref,
                        request.ticket_ref,
                        request.demand_ref,
                        request.workflow_id,
                        request.requested_selector_hash,
                        now,
                        now,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        assert row is not None
        return _row_run(row)

    def get_run(self, *, run_ref: str) -> AgentRun | None:
        with _connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM agent_runs WHERE run_ref = %s", (run_ref,))
                row = cur.fetchone()
                return _row_run(row) if row else None

    def update_run_status(self, *, run_ref: str, status: RunStatus, summary: dict | None = None) -> AgentRun:
        now = _now()
        ticket_ref = None
        if summary and summary.get("ticket_ref"):
            ticket_ref = str(summary["ticket_ref"])
        with _connect(self._dsn) as conn:
            with conn.cursor() as cur:
                if summary is not None and ticket_ref is not None:
                    cur.execute(
                        """
                        UPDATE agent_runs
                        SET status = %s, summary_json = %s::jsonb, ticket_ref = %s, updated_at = %s
                        WHERE run_ref = %s
                        RETURNING *
                        """,
                        (status.value, json.dumps(summary), ticket_ref, now, run_ref),
                    )
                elif summary is not None:
                    cur.execute(
                        """
                        UPDATE agent_runs
                        SET status = %s, summary_json = %s::jsonb, updated_at = %s
                        WHERE run_ref = %s
                        RETURNING *
                        """,
                        (status.value, json.dumps(summary), now, run_ref),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE agent_runs SET status = %s, updated_at = %s
                        WHERE run_ref = %s
                        RETURNING *
                        """,
                        (status.value, now, run_ref),
                    )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise KeyError(run_ref)
        return _row_run(row)

    def upsert_step(self, request: UpsertStepRequest) -> AgentRunStep:
        now = _now()
        with _connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT attempts FROM agent_run_steps WHERE step_ref = %s",
                    (request.step_ref,),
                )
                existing = cur.fetchone()
                attempts = (int(existing["attempts"]) if existing else 0) + (
                    1 if request.bump_attempts else 0
                )
                err = request.last_error_class.value if request.last_error_class else None
                cur.execute(
                    """
                    INSERT INTO agent_run_steps (
                        step_ref, run_ref, name, check_ref, status, worker_id, attempts,
                        last_error_class, result_ref, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (step_ref) DO UPDATE SET
                        run_ref = EXCLUDED.run_ref,
                        name = EXCLUDED.name,
                        check_ref = COALESCE(EXCLUDED.check_ref, agent_run_steps.check_ref),
                        status = EXCLUDED.status,
                        worker_id = COALESCE(EXCLUDED.worker_id, agent_run_steps.worker_id),
                        attempts = EXCLUDED.attempts,
                        last_error_class = COALESCE(EXCLUDED.last_error_class, agent_run_steps.last_error_class),
                        result_ref = COALESCE(EXCLUDED.result_ref, agent_run_steps.result_ref),
                        updated_at = EXCLUDED.updated_at
                    RETURNING *
                    """,
                    (
                        request.step_ref,
                        request.run_ref,
                        request.name,
                        request.check_ref,
                        request.status.value,
                        request.worker_id,
                        attempts,
                        err,
                        request.result_ref,
                        now,
                        now,
                    ),
                )
                step_row = cur.fetchone()
                cur.execute(
                    """
                    UPDATE agent_runs SET status = %s, updated_at = %s
                    WHERE run_ref = %s AND status IN ('accepted', 'pending')
                    """,
                    (RunStatus.RUNNING.value, now, request.run_ref),
                )
            conn.commit()
        assert step_row is not None
        return _row_step(step_row)

    def list_steps(self, *, run_ref: str) -> list[AgentRunStep]:
        with _connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM agent_run_steps WHERE run_ref = %s ORDER BY created_at",
                    (run_ref,),
                )
                return [_row_step(row) for row in cur.fetchall()]

    def claim_pending(
        self,
        *,
        worker_id: str,
        lease_until: datetime,
        limit: int = 1,
        name: str | None = None,
    ) -> list[AgentRunStep]:
        now = _now()
        with _connect(self._dsn) as conn:
            with conn.cursor() as cur:
                if name:
                    cur.execute(
                        """
                        SELECT step_ref FROM agent_run_steps
                        WHERE name = %s
                          AND (
                            status = 'pending'
                            OR (status = 'claimed' AND (claim_lease_until IS NULL OR claim_lease_until <= %s))
                          )
                        ORDER BY created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                        """,
                        (name, now, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT step_ref FROM agent_run_steps
                        WHERE status = 'pending'
                           OR (status = 'claimed' AND (claim_lease_until IS NULL OR claim_lease_until <= %s))
                        ORDER BY created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                        """,
                        (now, limit),
                    )
                ids = [r["step_ref"] for r in cur.fetchall()]
                claimed: list[AgentRunStep] = []
                for step_ref in ids:
                    cur.execute(
                        """
                        UPDATE agent_run_steps
                        SET status = 'claimed', worker_id = %s, claim_lease_until = %s,
                            attempts = attempts + 1, updated_at = %s
                        WHERE step_ref = %s
                        RETURNING *
                        """,
                        (worker_id, lease_until, now, step_ref),
                    )
                    row = cur.fetchone()
                    if row:
                        claimed.append(_row_step(row))
            conn.commit()
        return claimed

    def heartbeat(self, *, step_ref: str, worker_id: str, lease_until: datetime) -> None:
        with _connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT worker_id FROM agent_run_steps WHERE step_ref = %s",
                    (step_ref,),
                )
                row = cur.fetchone()
                if row is None:
                    raise KeyError(step_ref)
                if row["worker_id"] != worker_id:
                    raise PermissionError("worker mismatch")
                cur.execute(
                    """
                    UPDATE agent_run_steps
                    SET claim_lease_until = %s, updated_at = %s
                    WHERE step_ref = %s
                    """,
                    (lease_until, _now(), step_ref),
                )
            conn.commit()

    def complete_step(
        self,
        *,
        step_ref: str,
        status: str,
        result_ref: str | None = None,
        error_class: str | None = None,
    ) -> AgentRunStep:
        now = _now()
        with _connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_run_steps
                    SET status = %s, result_ref = COALESCE(%s, result_ref),
                        last_error_class = COALESCE(%s, last_error_class),
                        updated_at = %s
                    WHERE step_ref = %s
                    RETURNING *
                    """,
                    (status, result_ref, error_class, now, step_ref),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise KeyError(step_ref)
        return _row_step(row)
