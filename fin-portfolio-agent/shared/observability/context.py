"""Per-turn observability context via contextvars."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ObservabilityContext:
    """One chat turn: session stays across turns; trace_id is per-turn Langfuse id."""

    session_id: str
    user_id: str
    trace_id: str
    request_id: str
    env: str = "dev"
    prompt_name: Optional[str] = None
    prompt_version: Optional[str] = None
    prompt_source: Optional[str] = None
    prompt_label: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


obs_context_var: ContextVar[Optional[ObservabilityContext]] = ContextVar(
    "obs_context", default=None
)


def get_obs_context() -> Optional[ObservabilityContext]:
    return obs_context_var.get()


def set_obs_context(ctx: ObservabilityContext) -> None:
    obs_context_var.set(ctx)


def clear_obs_context() -> None:
    obs_context_var.set(None)
