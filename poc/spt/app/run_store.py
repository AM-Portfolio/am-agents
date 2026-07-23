"""Store facade — routes to JSON / DB / dual-write based on SPT_STORE."""

from __future__ import annotations

from typing import Any

from app.db.engine import store_mode
from app.stores import db_backend as db
from app.stores import json_backend as jb

# Re-export helpers used elsewhere
api_outcome_counts = jb.api_outcome_counts
slim_run_for_list = jb.slim_run_for_list


def _mode() -> str:
    return store_mode()


def list_runs(**kwargs: Any) -> tuple[list[dict[str, Any]], int]:
    mode = _mode()
    if mode == "json":
        return jb.list_runs(**kwargs)
    rows, total = db.list_runs(**kwargs)
    if mode == "dual" and total == 0:
        # Fallback if DB empty / miss during cutover
        jrows, jtotal = jb.list_runs(**kwargs)
        if jtotal:
            return jrows, jtotal
    return rows, total


def get_run(run_id: str) -> dict[str, Any] | None:
    mode = _mode()
    if mode == "json":
        return jb.get_run(run_id)
    row = db.get_run(run_id)
    if row is None and mode == "dual":
        return jb.get_run(run_id)
    return row


def save_run(record: dict[str, Any]) -> dict[str, Any]:
    mode = _mode()
    if mode == "json":
        return jb.save_run(record)
    if mode == "dual":
        saved = db.save_run(record)
        try:
            jb.save_run(dict(saved))
        except Exception:
            pass
        return saved
    return db.save_run(record)


def update_run(run_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    mode = _mode()
    if mode == "json":
        return jb.update_run(run_id, patch)
    if mode == "dual":
        row = db.update_run(run_id, patch)
        try:
            jb.update_run(run_id, patch)
        except Exception:
            pass
        if row is None:
            return jb.update_run(run_id, patch)
        return row
    return db.update_run(run_id, patch)


def increment_run_progress(run_id: str, **kwargs: Any) -> dict[str, Any] | None:
    mode = _mode()
    if mode == "json":
        return jb.increment_run_progress(run_id, **kwargs)
    if mode == "dual":
        result = db.increment_run_progress(run_id, **kwargs)
        try:
            jb.increment_run_progress(run_id, **kwargs)
        except Exception:
            pass
        if result and result.get("reason") == "missing":
            return jb.increment_run_progress(run_id, **kwargs)
        return result
    return db.increment_run_progress(run_id, **kwargs)


def list_configs(**kwargs: Any) -> list[dict[str, Any]]:
    mode = _mode()
    if mode == "json":
        return jb.list_configs(**kwargs)
    rows = db.list_configs(**kwargs)
    if mode == "dual" and not rows:
        return jb.list_configs(**kwargs)
    return rows


def get_config(config_id: str) -> dict[str, Any] | None:
    mode = _mode()
    if mode == "json":
        return jb.get_config(config_id)
    row = db.get_config(config_id)
    if row is None and mode == "dual":
        return jb.get_config(config_id)
    return row


def save_config(record: dict[str, Any]) -> dict[str, Any]:
    mode = _mode()
    if mode == "json":
        return jb.save_config(record)
    if mode == "dual":
        saved = db.save_config(record)
        try:
            jb.save_config(dict(saved))
        except Exception:
            pass
        return saved
    return db.save_config(record)


def delete_config(config_id: str) -> bool:
    mode = _mode()
    if mode == "json":
        return jb.delete_config(config_id)
    ok = db.delete_config(config_id)
    if mode == "dual":
        try:
            jb.delete_config(config_id)
        except Exception:
            pass
    return ok


def count_running() -> int:
    mode = _mode()
    if mode == "json":
        rows, _ = jb.list_runs(limit=500, status="running")
        return len(rows)
    return db.count_running()
