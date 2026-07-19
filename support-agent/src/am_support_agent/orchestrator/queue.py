"""Temporal task queue resolution — use existing support-agent-v2."""

from __future__ import annotations

import os

SHARED_QUEUE = "support-agent-v2"
LEGACY_PLATFORM_QUEUE = "agent-platform"


def deployment_environment() -> str:
    raw = (
        os.getenv("DEPLOYMENT_ENVIRONMENT")
        or os.getenv("SUPPORT_AGENT_RUNTIME_MODE")
        or os.getenv("APP_ENV")
        or ""
    ).strip().lower()
    if raw in {"development", "local", "test"}:
        return "dev" if raw != "test" else "test"
    return raw


def default_queue_for_env(env: str | None = None) -> str:
    """Always the shared support-agent-v2 queue (already provisioned)."""
    del env  # retained for API compatibility
    return SHARED_QUEUE


def resolve_task_queue(*, require_env_suffix: bool = False) -> str:
    """Resolve Temporal task queue — prefer TEMPORAL_TASK_QUEUE, else support-agent-v2."""
    del require_env_suffix  # env-suffixed queues are not used
    explicit = (os.getenv("TEMPORAL_TASK_QUEUE") or "").strip()
    if explicit == LEGACY_PLATFORM_QUEUE:
        raise ValueError(
            "Refusing legacy Temporal queue 'agent-platform'. "
            f"Use TEMPORAL_TASK_QUEUE={SHARED_QUEUE}"
        )
    if explicit:
        return explicit
    return SHARED_QUEUE


def assert_safe_task_queue(queue: str) -> None:
    if queue == LEGACY_PLATFORM_QUEUE:
        raise SystemExit(
            "Refusing to bind support-agent worker to legacy queue 'agent-platform'. "
            f"Use TEMPORAL_TASK_QUEUE={SHARED_QUEUE}"
        )


__all__ = [
    "SHARED_QUEUE",
    "LEGACY_PLATFORM_QUEUE",
    "deployment_environment",
    "default_queue_for_env",
    "resolve_task_queue",
    "assert_safe_task_queue",
]
