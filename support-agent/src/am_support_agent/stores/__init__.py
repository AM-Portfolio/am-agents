"""Task run-store factory."""

from __future__ import annotations

import os

from am_support_agent.stores.episodes import (
    MemoryEpisodeStore,
    MemoryFeedbackStore,
    build_episode_store,
    build_feedback_store,
)
from am_support_agent.stores.run_store import (
    MemoryTaskRunStore,
    SqliteTaskRunStore,
    TaskRun,
    TaskRunStore,
)
from am_support_agent.stores.workflow_ledger import (
    MemoryWorkflowLedger,
    SqliteWorkflowLedger,
    WorkflowKind,
    WorkflowLedger,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStep,
    WorkflowStepStatus,
    build_workflow_ledger,
    new_run_ref,
)


def build_task_run_store() -> TaskRunStore:
    backend = os.getenv("SUPPORT_AGENT_RUNSTORE", "memory").strip().lower()
    if backend == "memory":
        return MemoryTaskRunStore()
    if backend == "sqlite":
        path = os.getenv(
            "SUPPORT_AGENT_SQLITE_PATH", "/data/support-agent-runs.db"
        )
        return SqliteTaskRunStore(path)
    if backend == "postgres":
        dsn = (
            os.getenv("SUPPORT_AGENT_DATABASE_URL", "").strip()
            or os.getenv("DATABASE_URL", "").strip()
        )
        if not dsn:
            raise RuntimeError(
                "SUPPORT_AGENT_RUNSTORE=postgres requires "
                "SUPPORT_AGENT_DATABASE_URL (or DATABASE_URL). "
                "Uses dedicated schema support_agent.task_runs — never legacy "
                "agent_runs from platform-adapters. "
                "Install: pip install 'am-support-agent[postgres]'"
            )
        from am_support_agent.stores.postgres import PostgresTaskRunStore

        return PostgresTaskRunStore(dsn)
    raise ValueError(f"unsupported SUPPORT_AGENT_RUNSTORE: {backend}")


__all__ = [
    "TaskRun",
    "TaskRunStore",
    "MemoryTaskRunStore",
    "SqliteTaskRunStore",
    "build_task_run_store",
    "MemoryEpisodeStore",
    "MemoryFeedbackStore",
    "build_episode_store",
    "build_feedback_store",
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
