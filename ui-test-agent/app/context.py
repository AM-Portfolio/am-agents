from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from playwright.async_api import Page

    from app.llm.base import LLMClient


@dataclass
class TestRunContext:
    test_id: str
    session_id: str
    profile: str
    llm_client: LLMClient
    page: Optional[Page] = None
    commit_sha: Optional[str] = None
    branch: str = "main"
    baseline_mode: str = "compare"
    action_log: list[dict[str, Any]] = field(default_factory=list)
    step_timings: list[dict[str, Any]] = field(default_factory=list)
    started_at_iso: str = ""
    finished_at_iso: str = ""
    _started_at_monotonic: float = 0.0

    def mark_run_start(self) -> None:
        self._started_at_monotonic = time.perf_counter()
        self.started_at_iso = datetime.now(timezone.utc).isoformat()

    def total_duration_ms(self) -> float | None:
        if not self._started_at_monotonic:
            return None
        return (time.perf_counter() - self._started_at_monotonic) * 1000

    def log_action(self, action: str, *, duration_ms: float | None = None, **details: Any) -> None:
        entry: dict[str, Any] = {
            "action": action,
            "ts": datetime.now(timezone.utc).isoformat(),
            **details,
        }
        if duration_ms is not None:
            entry["duration_ms"] = round(duration_ms, 1)
        self.action_log.append(entry)

    def record_step_timing(
        self,
        *,
        index: int,
        name: str,
        action: str,
        phase: str,
        duration_ms: float,
        status: str = "ok",
        error: str | None = None,
    ) -> None:
        row: dict[str, Any] = {
            "index": index + 1,
            "name": name,
            "action": action,
            "phase": phase,
            "duration_ms": round(duration_ms, 1),
            "status": status,
        }
        if error:
            row["error"] = error
        self.step_timings.append(row)


def get_test_context(config: dict) -> TestRunContext:
    ctx = config.get("configurable", {}).get("test_context")
    if ctx is None:
        raise RuntimeError("TestRunContext missing from LangGraph config")
    return ctx
