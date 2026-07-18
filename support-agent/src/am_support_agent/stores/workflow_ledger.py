"""Workflow run ledger — distinct from A2A task_runs.

Tracks incident/SPT parent/child runs, steps, claims, evidence refs.
Never uses legacy agent_runs / agent_run_steps.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(UTC).isoformat()


def new_run_ref(prefix: str = "run") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


class WorkflowKind(str, Enum):
    ALERT_INCIDENT = "alert_incident"
    SPT = "spt"
    HANDOFF = "handoff"
    A2A = "a2a"


class WorkflowRunStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    NEEDS_HUMAN = "needs_human"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowRun(BaseModel):
    run_ref: str
    kind: WorkflowKind
    status: WorkflowRunStatus
    tracking_id: str = ""
    workflow_id: str = ""
    parent_run_ref: str | None = None
    demand_ref: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    validation_json: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class WorkflowStep(BaseModel):
    step_ref: str
    run_ref: str
    name: str
    status: WorkflowStepStatus
    result_ref: str = ""
    attempts: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class WorkflowLedger(Protocol):
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
    ) -> WorkflowRun: ...

    def get_run(self, run_ref: str) -> WorkflowRun | None: ...

    def get_by_workflow_id(self, workflow_id: str) -> WorkflowRun | None: ...

    def update_run(
        self,
        run_ref: str,
        *,
        status: WorkflowRunStatus | None = None,
        workflow_id: str | None = None,
        summary: dict[str, Any] | None = None,
        evidence_refs: list[str] | None = None,
        validation_json: dict[str, Any] | None = None,
    ) -> WorkflowRun: ...

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
    ) -> WorkflowStep: ...

    def list_steps(self, run_ref: str) -> list[WorkflowStep]: ...

    def handoff(
        self,
        *,
        from_run_ref: str,
        to_kind: WorkflowKind | str,
        depth: int = 1,
        context: dict[str, Any] | None = None,
    ) -> WorkflowRun: ...

    def ready(self) -> bool: ...


class MemoryWorkflowLedger:
    """In-process workflow ledger for tests and single-replica local runs."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: dict[str, WorkflowRun] = {}
        self._steps: dict[str, list[WorkflowStep]] = {}
        self._by_workflow: dict[str, str] = {}

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
            self._runs[ref] = run
            self._steps.setdefault(ref, [])
            if workflow_id:
                self._by_workflow[workflow_id] = ref
        return run.model_copy(deep=True)

    def get_run(self, run_ref: str) -> WorkflowRun | None:
        with self._lock:
            run = self._runs.get(run_ref)
            return run.model_copy(deep=True) if run else None

    def get_by_workflow_id(self, workflow_id: str) -> WorkflowRun | None:
        with self._lock:
            ref = self._by_workflow.get(workflow_id)
            if not ref:
                return None
            run = self._runs.get(ref)
            return run.model_copy(deep=True) if run else None

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
        with self._lock:
            run = self._runs.get(run_ref)
            if run is None:
                raise KeyError(f"unknown run_ref: {run_ref}")
            data = run.model_dump()
            if status is not None:
                data["status"] = status
            if workflow_id is not None:
                data["workflow_id"] = workflow_id
                self._by_workflow[workflow_id] = run_ref
            if summary is not None:
                data["summary"] = {**(data.get("summary") or {}), **summary}
            if evidence_refs is not None:
                data["evidence_refs"] = list(evidence_refs)
            if validation_json is not None:
                data["validation_json"] = validation_json
            data["updated_at"] = _now()
            updated = WorkflowRun.model_validate(data)
            self._runs[run_ref] = updated
            return updated.model_copy(deep=True)

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
        with self._lock:
            if run_ref not in self._runs:
                raise KeyError(f"unknown run_ref: {run_ref}")
            steps = self._steps.setdefault(run_ref, [])
            ref = step_ref or f"{run_ref}:{name}"
            existing = next((s for s in steps if s.step_ref == ref), None)
            now = _now()
            if existing is None:
                step = WorkflowStep(
                    step_ref=ref,
                    run_ref=run_ref,
                    name=name,
                    status=status,
                    result_ref=result_ref,
                    attempts=1 if bump_attempts else 0,
                    detail=dict(detail or {}),
                    created_at=now,
                    updated_at=now,
                )
                steps.append(step)
                return step.model_copy(deep=True)
            data = existing.model_dump()
            data["status"] = status
            data["result_ref"] = result_ref or data["result_ref"]
            if bump_attempts:
                data["attempts"] = int(data.get("attempts") or 0) + 1
            if detail is not None:
                data["detail"] = {**(data.get("detail") or {}), **detail}
            data["updated_at"] = now
            updated = WorkflowStep.model_validate(data)
            for i, step in enumerate(steps):
                if step.step_ref == ref:
                    steps[i] = updated
                    break
            return updated.model_copy(deep=True)

    def list_steps(self, run_ref: str) -> list[WorkflowStep]:
        with self._lock:
            return [s.model_copy(deep=True) for s in self._steps.get(run_ref, [])]

    def handoff(
        self,
        *,
        from_run_ref: str,
        to_kind: WorkflowKind | str,
        depth: int = 1,
        context: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        if depth < 1:
            raise ValueError("handoff depth must be >= 1")
        parent = self.get_run(from_run_ref)
        if parent is None:
            raise KeyError(f"unknown from_run_ref: {from_run_ref}")
        kind = (
            to_kind
            if isinstance(to_kind, WorkflowKind)
            else WorkflowKind(str(to_kind))
        )
        child = self.create_run(
            kind=kind,
            tracking_id=parent.tracking_id,
            parent_run_ref=from_run_ref,
            summary={
                "handoff_depth": depth,
                "context": dict(context or {}),
            },
        )
        self.upsert_step(
            run_ref=from_run_ref,
            name="handoff",
            status=WorkflowStepStatus.PASSED,
            result_ref=child.run_ref,
            bump_attempts=True,
            detail={"to_kind": kind.value, "depth": depth},
        )
        return child

    def ready(self) -> bool:
        return True


class SqliteWorkflowLedger:
    """SQLite workflow ledger (local/CI; not multi-replica HA)."""

    def __init__(self, path: str) -> None:
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_ref TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    tracking_id TEXT NOT NULL DEFAULT '',
                    workflow_id TEXT NOT NULL DEFAULT '',
                    parent_run_ref TEXT,
                    demand_ref TEXT NOT NULL DEFAULT '',
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    validation_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS workflow_runs_workflow_id
                    ON workflow_runs(workflow_id);
                CREATE TABLE IF NOT EXISTS workflow_steps (
                    step_ref TEXT PRIMARY KEY,
                    run_ref TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_ref TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

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
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO workflow_runs (
                    run_ref, kind, status, tracking_id, workflow_id, parent_run_ref,
                    demand_ref, summary_json, evidence_json, validation_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', NULL, ?, ?)
                """,
                (
                    ref,
                    kind.value,
                    WorkflowRunStatus.ACCEPTED.value,
                    tracking_id,
                    workflow_id,
                    parent_run_ref,
                    demand_ref,
                    json.dumps(summary or {}),
                    now,
                    now,
                ),
            )
            self._conn.commit()
        run = self.get_run(ref)
        assert run is not None
        return run

    def get_run(self, run_ref: str) -> WorkflowRun | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workflow_runs WHERE run_ref = ?",
                (run_ref,),
            ).fetchone()
        return self._row_run(row) if row else None

    def get_by_workflow_id(self, workflow_id: str) -> WorkflowRun | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workflow_runs WHERE workflow_id = ? ORDER BY created_at DESC LIMIT 1",
                (workflow_id,),
            ).fetchone()
        return self._row_run(row) if row else None

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
        current = self.get_run(run_ref)
        if current is None:
            raise KeyError(f"unknown run_ref: {run_ref}")
        merged_summary = {**current.summary, **(summary or {})} if summary else current.summary
        with self._lock:
            self._conn.execute(
                """
                UPDATE workflow_runs SET
                    status = ?,
                    workflow_id = ?,
                    summary_json = ?,
                    evidence_json = ?,
                    validation_json = ?,
                    updated_at = ?
                WHERE run_ref = ?
                """,
                (
                    (status or current.status).value,
                    workflow_id if workflow_id is not None else current.workflow_id,
                    json.dumps(merged_summary),
                    json.dumps(
                        evidence_refs
                        if evidence_refs is not None
                        else current.evidence_refs
                    ),
                    json.dumps(
                        validation_json
                        if validation_json is not None
                        else current.validation_json
                    )
                    if (validation_json is not None or current.validation_json is not None)
                    else None,
                    _now(),
                    run_ref,
                ),
            )
            self._conn.commit()
        run = self.get_run(run_ref)
        assert run is not None
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
        if self.get_run(run_ref) is None:
            raise KeyError(f"unknown run_ref: {run_ref}")
        ref = step_ref or f"{run_ref}:{name}"
        now = _now()
        with self._lock:
            existing = self._conn.execute(
                "SELECT * FROM workflow_steps WHERE step_ref = ?",
                (ref,),
            ).fetchone()
            if existing is None:
                self._conn.execute(
                    """
                    INSERT INTO workflow_steps (
                        step_ref, run_ref, name, status, result_ref, attempts,
                        detail_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ref,
                        run_ref,
                        name,
                        status.value,
                        result_ref,
                        1 if bump_attempts else 0,
                        json.dumps(detail or {}),
                        now,
                        now,
                    ),
                )
            else:
                attempts = int(existing["attempts"] or 0) + (1 if bump_attempts else 0)
                prior_detail = json.loads(existing["detail_json"] or "{}")
                self._conn.execute(
                    """
                    UPDATE workflow_steps SET
                        status = ?, result_ref = ?, attempts = ?, detail_json = ?,
                        updated_at = ?
                    WHERE step_ref = ?
                    """,
                    (
                        status.value,
                        result_ref or existing["result_ref"],
                        attempts,
                        json.dumps({**prior_detail, **(detail or {})}),
                        now,
                        ref,
                    ),
                )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM workflow_steps WHERE step_ref = ?",
                (ref,),
            ).fetchone()
        assert row is not None
        return self._row_step(row)

    def list_steps(self, run_ref: str) -> list[WorkflowStep]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM workflow_steps WHERE run_ref = ? ORDER BY created_at",
                (run_ref,),
            ).fetchall()
        return [self._row_step(r) for r in rows]

    def handoff(
        self,
        *,
        from_run_ref: str,
        to_kind: WorkflowKind | str,
        depth: int = 1,
        context: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        if depth < 1:
            raise ValueError("handoff depth must be >= 1")
        parent = self.get_run(from_run_ref)
        if parent is None:
            raise KeyError(f"unknown from_run_ref: {from_run_ref}")
        kind = (
            to_kind
            if isinstance(to_kind, WorkflowKind)
            else WorkflowKind(str(to_kind))
        )
        child = self.create_run(
            kind=kind,
            tracking_id=parent.tracking_id,
            parent_run_ref=from_run_ref,
            summary={"handoff_depth": depth, "context": dict(context or {})},
        )
        self.upsert_step(
            run_ref=from_run_ref,
            name="handoff",
            status=WorkflowStepStatus.PASSED,
            result_ref=child.run_ref,
            bump_attempts=True,
            detail={"to_kind": kind.value, "depth": depth},
        )
        return child

    def ready(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _row_run(row: sqlite3.Row) -> WorkflowRun:
        return WorkflowRun(
            run_ref=row["run_ref"],
            kind=WorkflowKind(row["kind"]),
            status=WorkflowRunStatus(row["status"]),
            tracking_id=row["tracking_id"] or "",
            workflow_id=row["workflow_id"] or "",
            parent_run_ref=row["parent_run_ref"],
            demand_ref=row["demand_ref"] or "",
            summary=json.loads(row["summary_json"] or "{}"),
            evidence_refs=json.loads(row["evidence_json"] or "[]"),
            validation_json=json.loads(row["validation_json"])
            if row["validation_json"]
            else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_step(row: sqlite3.Row) -> WorkflowStep:
        return WorkflowStep(
            step_ref=row["step_ref"],
            run_ref=row["run_ref"],
            name=row["name"],
            status=WorkflowStepStatus(row["status"]),
            result_ref=row["result_ref"] or "",
            attempts=int(row["attempts"] or 0),
            detail=json.loads(row["detail_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def build_workflow_ledger() -> WorkflowLedger:
    import os

    backend = os.getenv("SUPPORT_AGENT_WORKFLOW_STORE", "").strip().lower()
    if not backend:
        # Default: share task-store backend when set, else memory.
        backend = os.getenv("SUPPORT_AGENT_RUNSTORE", "memory").strip().lower()
    if backend == "memory":
        return MemoryWorkflowLedger()
    if backend == "sqlite":
        path = os.getenv(
            "SUPPORT_AGENT_WORKFLOW_SQLITE_PATH",
            os.getenv("SUPPORT_AGENT_SQLITE_PATH", "/data/support-agent-runs.db"),
        )
        # Distinct file name when sharing default path with task store.
        if path.endswith("support-agent-runs.db"):
            path = path.replace("support-agent-runs.db", "support-agent-workflows.db")
        return SqliteWorkflowLedger(path)
    if backend == "postgres":
        # Postgres implementation lands with composition root; fail closed for now.
        raise RuntimeError(
            "SUPPORT_AGENT_WORKFLOW_STORE=postgres not implemented yet; "
            "use memory or sqlite until the dedicated workflow_runs schema ships."
        )
    raise ValueError(f"unsupported SUPPORT_AGENT_WORKFLOW_STORE: {backend}")


__all__ = [
    "WorkflowKind",
    "WorkflowRunStatus",
    "WorkflowStepStatus",
    "WorkflowRun",
    "WorkflowStep",
    "WorkflowLedger",
    "MemoryWorkflowLedger",
    "SqliteWorkflowLedger",
    "build_workflow_ledger",
    "new_run_ref",
]
