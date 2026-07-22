"""In-process registry of active k6 runs (requires replicas=1)."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActiveRun:
    run_id: str
    proc: subprocess.Popen[str] | None = None
    cancel_requested: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


_lock = threading.Lock()
_runs: dict[str, ActiveRun] = {}
_cancelled: set[str] = set()


def register(run_id: str, *, meta: dict[str, Any] | None = None) -> ActiveRun:
    with _lock:
        existing = _runs.get(run_id)
        if existing is not None:
            if meta:
                existing.meta.update(meta)
            return existing
        row = ActiveRun(run_id=run_id, meta=dict(meta or {}))
        if run_id in _cancelled:
            row.cancel_requested = True
        _runs[run_id] = row
        return row


def begin_run(run_id: str, *, meta: dict[str, Any] | None = None) -> ActiveRun:
    """Start a fresh run slot (clears prior cancel flag for this id)."""
    with _lock:
        _cancelled.discard(run_id)
        row = ActiveRun(run_id=run_id, meta=dict(meta or {}))
        _runs[run_id] = row
        return row


def attach_proc(run_id: str, proc: subprocess.Popen[str]) -> None:
    with _lock:
        row = _runs.get(run_id)
        if row is None:
            row = ActiveRun(run_id=run_id)
            _runs[run_id] = row
        row.proc = proc
        if row.cancel_requested and proc.poll() is None:
            _kill_proc(proc)


def is_cancel_requested(run_id: str) -> bool:
    with _lock:
        if run_id in _cancelled:
            return True
        row = _runs.get(run_id)
        return bool(row and row.cancel_requested)


def request_stop(run_id: str) -> dict[str, Any]:
    """Mark cancel and kill k6 if running. Returns status dict."""
    with _lock:
        _cancelled.add(run_id)
        row = _runs.get(run_id)
        if row is None:
            return {"ok": False, "reason": "not_active"}
        row.cancel_requested = True
        proc = row.proc
    if proc is not None and proc.poll() is None:
        _kill_proc(proc)
        return {"ok": True, "killed": True}
    return {"ok": True, "killed": False, "reason": "no_proc_yet"}


def unregister(run_id: str) -> None:
    with _lock:
        _runs.pop(run_id, None)


def clear_cancelled(run_id: str) -> None:
    with _lock:
        _cancelled.discard(run_id)


def active_ids() -> list[str]:
    with _lock:
        return list(_runs.keys())


def _kill_proc(proc: subprocess.Popen[str]) -> None:
    try:
        proc.kill()
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
