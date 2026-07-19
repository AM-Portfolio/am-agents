"""Postgres workflow ledger — support_agent.workflow_runs / workflow_steps."""

from __future__ import annotations

import json
import threading
from typing import Any

from am_support_agent.stores.migrations import apply_migrations
from am_support_agent.stores.workflow_ledger import (
    WorkflowKind,
    WorkflowLedger,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStep,
    WorkflowStepStatus,
    _now,
    new_run_ref,
)


class PostgresWorkflowLedger:
    name = "postgres-workflow-ledger"

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise RuntimeError(
                "SUPPORT_AGENT_WORKFLOW_STORE=postgres requires psycopg. "
                "Install with: pip install 'am-support-agent[postgres]'"
            ) from exc
        self._Jsonb = Jsonb
        self._dsn = dsn
        self._lock = threading.RLock()
        self._conn = psycopg.connect(dsn, row_factory=dict_row)
        self._conn.autocommit = False
        apply_migrations(self._conn)

    def ready(self) -> bool:
        try:
            with self._lock:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                self._conn.commit()
            return True
        except Exception:  # noqa: BLE001
            try:
                self._conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            return False

    def create_run(
        self,
        *,
        kind: WorkflowKind,
        tracking_id: str = "",
        workflow_id: str = "",
        parent_run_ref: str | None = None,
        demand_ref: str = "",
        summary: dict[str, Any] | None = None,
        run_ref: str | None = None,
    ) -> WorkflowRun:
        now = _now()
        ref = run_ref or new_run_ref()
        run = WorkflowRun(
            run_ref=ref,
            kind=kind,
            status=WorkflowRunStatus.ACCEPTED,
            tracking_id=tracking_id,
            workflow_id=workflow_id,
            parent_run_ref=parent_run_ref,
            demand_ref=demand_ref,
            summary=dict(summary or {}),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO support_agent.workflow_runs (
                        run_ref, kind, status, tracking_id, workflow_id,
                        parent_run_ref, demand_ref, summary, evidence_refs,
                        validation_json, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        NULL, %s::timestamptz, %s::timestamptz
                    )
                    """,
                    (
                        run.run_ref,
                        run.kind.value,
                        run.status.value,
                        run.tracking_id,
                        run.workflow_id,
                        run.parent_run_ref,
                        run.demand_ref,
                        self._Jsonb(run.summary),
                        self._Jsonb(run.evidence_refs),
                        now,
                        now,
                    ),
                )
            self._conn.commit()
        return run

    def get_run(self, run_ref: str) -> WorkflowRun | None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM support_agent.workflow_runs WHERE run_ref = %s",
                    (run_ref,),
                )
                row = cur.fetchone()
            self._conn.commit()
        return self._row_to_run(row) if row else None

    def get_by_workflow_id(self, workflow_id: str) -> WorkflowRun | None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM support_agent.workflow_runs
                    WHERE workflow_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (workflow_id,),
                )
                row = cur.fetchone()
            self._conn.commit()
        return self._row_to_run(row) if row else None

    def update_run(
        self,
        run_ref: str,
        *,
        status: WorkflowRunStatus | None = None,
        workflow_id: str | None = None,
        summary: dict[str, Any] | None = None,
        evidence_refs: list[str] | None = None,
        validation_json: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        run = self.get_run(run_ref)
        if run is None:
            raise KeyError(f"unknown run_ref: {run_ref}")
        updates: dict[str, Any] = {"updated_at": _now()}
        if status is not None:
            updates["status"] = status
        if workflow_id is not None:
            updates["workflow_id"] = workflow_id
        if summary is not None:
            updates["summary"] = dict(summary)
        if evidence_refs is not None:
            updates["evidence_refs"] = list(evidence_refs)
        if validation_json is not None:
            updates["validation_json"] = dict(validation_json)
        run = run.model_copy(update=updates)
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE support_agent.workflow_runs
                    SET status = %s,
                        workflow_id = %s,
                        summary = %s,
                        evidence_refs = %s,
                        validation_json = %s,
                        updated_at = %s::timestamptz
                    WHERE run_ref = %s
                    """,
                    (
                        run.status.value,
                        run.workflow_id,
                        self._Jsonb(run.summary),
                        self._Jsonb(run.evidence_refs),
                        self._Jsonb(run.validation_json) if run.validation_json else None,
                        run.updated_at,
                        run_ref,
                    ),
                )
            self._conn.commit()
        return run

    def upsert_step(
        self,
        *,
        run_ref: str,
        name: str,
        status: WorkflowStepStatus,
        step_ref: str | None = None,
        result_ref: str = "",
        bump_attempts: bool = False,
        detail: dict[str, Any] | None = None,
    ) -> WorkflowStep:
        now = _now()
        ref = step_ref or f"{run_ref}:{name}"
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM support_agent.workflow_steps WHERE step_ref = %s",
                    (ref,),
                )
                existing = cur.fetchone()
                attempts = int(existing["attempts"]) if existing else 0
                if bump_attempts:
                    attempts += 1
                step = WorkflowStep(
                    step_ref=ref,
                    run_ref=run_ref,
                    name=name,
                    status=status,
                    result_ref=result_ref,
                    attempts=attempts,
                    detail=dict(detail or (existing or {}).get("detail") or {}),
                    created_at=str(
                        (existing or {}).get("created_at") or now
                    ),
                    updated_at=now,
                )
                cur.execute(
                    """
                    INSERT INTO support_agent.workflow_steps (
                        step_ref, run_ref, name, status, result_ref, attempts,
                        detail, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s::timestamptz, %s::timestamptz
                    )
                    ON CONFLICT (step_ref) DO UPDATE SET
                        status = EXCLUDED.status,
                        result_ref = EXCLUDED.result_ref,
                        attempts = EXCLUDED.attempts,
                        detail = EXCLUDED.detail,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        step.step_ref,
                        step.run_ref,
                        step.name,
                        step.status.value,
                        step.result_ref,
                        step.attempts,
                        self._Jsonb(step.detail),
                        step.created_at if "T" in str(step.created_at) else now,
                        now,
                    ),
                )
            self._conn.commit()
        return step

    def list_steps(self, run_ref: str) -> list[WorkflowStep]:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM support_agent.workflow_steps
                    WHERE run_ref = %s
                    ORDER BY created_at ASC
                    """,
                    (run_ref,),
                )
                rows = cur.fetchall()
            self._conn.commit()
        return [self._row_to_step(r) for r in rows]

    def handoff(
        self,
        *,
        from_run_ref: str,
        to_kind: WorkflowKind | str,
        depth: int = 1,
        context: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        parent = self.get_run(from_run_ref)
        if parent is None:
            raise KeyError(f"unknown run_ref: {from_run_ref}")
        kind = to_kind if isinstance(to_kind, WorkflowKind) else WorkflowKind(to_kind)
        child = self.create_run(
            kind=kind,
            tracking_id=parent.tracking_id,
            parent_run_ref=from_run_ref,
            summary={"depth": depth, "context": dict(context or {})},
        )
        self.upsert_step(
            run_ref=from_run_ref,
            name="handoff",
            status=WorkflowStepStatus.PASSED,
            result_ref=child.run_ref,
            detail={"to_kind": kind.value, "depth": depth},
        )
        return child

    def _row_to_run(self, row: dict[str, Any]) -> WorkflowRun:
        created = row.get("created_at")
        updated = row.get("updated_at")
        return WorkflowRun(
            run_ref=str(row["run_ref"]),
            kind=WorkflowKind(str(row["kind"])),
            status=WorkflowRunStatus(str(row["status"])),
            tracking_id=str(row.get("tracking_id") or ""),
            workflow_id=str(row.get("workflow_id") or ""),
            parent_run_ref=row.get("parent_run_ref"),
            demand_ref=str(row.get("demand_ref") or ""),
            summary=dict(row.get("summary") or {}),
            evidence_refs=list(row.get("evidence_refs") or []),
            validation_json=row.get("validation_json"),
            created_at=created.isoformat() if hasattr(created, "isoformat") else str(created),
            updated_at=updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
        )

    def _row_to_step(self, row: dict[str, Any]) -> WorkflowStep:
        created = row.get("created_at")
        updated = row.get("updated_at")
        return WorkflowStep(
            step_ref=str(row["step_ref"]),
            run_ref=str(row["run_ref"]),
            name=str(row["name"]),
            status=WorkflowStepStatus(str(row["status"])),
            result_ref=str(row.get("result_ref") or ""),
            attempts=int(row.get("attempts") or 0),
            detail=dict(row.get("detail") or {}),
            created_at=created.isoformat() if hasattr(created, "isoformat") else str(created),
            updated_at=updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
        )


__all__ = ["PostgresWorkflowLedger"]
