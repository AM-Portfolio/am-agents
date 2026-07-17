"""Concurrent SPT parent-run guard (process-local)."""

from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_active_spt: set[str] = set()


def max_concurrent_runs() -> int:
    return int(os.getenv("SPT_MAX_CONCURRENT_RUNS", "3"))


def try_acquire_spt(workflow_id: str) -> None:
    with _lock:
        if len(_active_spt) >= max_concurrent_runs():
            raise PermissionError(
                f"SPT_MAX_CONCURRENT_RUNS={max_concurrent_runs()} reached"
            )
        _active_spt.add(workflow_id)


def release_spt(workflow_id: str) -> None:
    with _lock:
        _active_spt.discard(workflow_id)


def active_count() -> int:
    with _lock:
        return len(_active_spt)
