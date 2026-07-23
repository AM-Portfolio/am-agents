from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

_lock = threading.Lock()
RUNS_FILE = "runs.json"
CONFIGS_FILE = "configs.json"


def _data_dir() -> Path:
    path = Path(settings.data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(name: str) -> list[dict[str, Any]]:
    path = _data_dir() / name
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _write_json(name: str, rows: list[dict[str, Any]]) -> None:
    path = _data_dir() / name
    path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")


def api_outcome_counts(api_summary: list[dict[str, Any]] | None) -> dict[str, int]:
    """Count passed / failed APIs from a run's api_summary rows."""
    rows = api_summary or []
    passed = 0
    failed = 0
    for row in rows:
        if row.get("checks_passed") is True:
            passed += 1
        elif row.get("checks_passed") is False:
            failed += 1
        elif row.get("live_state") in {"completed", "done"} and row.get("status") != "pending":
            # live stream finished without check flag — ignore
            continue
        elif row.get("fail_count") and int(row.get("fail_count") or 0) > 0 and int(row.get("pass_count") or 0) == 0:
            failed += 1
        elif row.get("pass_count") and int(row.get("pass_count") or 0) > 0 and int(row.get("fail_count") or 0) == 0:
            passed += 1
    return {"api_pass_count": passed, "api_fail_count": failed, "api_count": len(rows)}


def slim_run_for_list(row: dict[str, Any]) -> dict[str, Any]:
    """Lightweight run row for sidebar list (no k6 scripts / tokens)."""
    payloads = row.get("payloads_used") or {}
    bench = payloads.get("bench_run") or {}
    auth = payloads.get("auth_env") or {}
    counts = {
        "api_pass_count": row.get("api_pass_count"),
        "api_fail_count": row.get("api_fail_count"),
        "api_count": row.get("api_count"),
    }
    if counts["api_pass_count"] is None or counts["api_fail_count"] is None:
        derived = api_outcome_counts(row.get("api_summary"))
        if counts["api_pass_count"] is None:
            counts["api_pass_count"] = derived["api_pass_count"]
        if counts["api_fail_count"] is None:
            counts["api_fail_count"] = derived["api_fail_count"]
        if not counts["api_count"]:
            counts["api_count"] = derived["api_count"] or row.get("api_count")
    return {
        "id": row.get("id"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "status": row.get("status"),
        "passed": row.get("passed"),
        "runner": row.get("runner"),
        "run_profile": row.get("run_profile"),
        "config_id": row.get("config_id"),
        "config_name": row.get("config_name"),
        "service": row.get("service"),
        "environment": row.get("environment"),
        "test_type": row.get("test_type"),
        "triggered_by": row.get("triggered_by"),
        "target_url": row.get("target_url"),
        "api_count": counts["api_count"],
        "api_pass_count": counts["api_pass_count"],
        "api_fail_count": counts["api_fail_count"],
        "error": row.get("error"),
        "audience": row.get("audience"),
        "caller_role": row.get("caller_role"),
        "vus": row.get("vus") if row.get("vus") is not None else bench.get("vus"),
        "iterations": row.get("iterations") if row.get("iterations") is not None else bench.get("iterations"),
        "duration": row.get("duration") if row.get("duration") is not None else bench.get("duration"),
        "fail_pct": row.get("fail_pct"),
        "p90_ms": row.get("p90_ms"),
        "rps": row.get("rps"),
        "auth_username": row.get("auth_username") or auth.get("username"),
        "payloads_used": {
            "bench_run": bench,
            "auth_env": {
                k: auth[k]
                for k in ("username", "user_id", "authenticated")
                if k in auth
            },
            "run_params": payloads.get("run_params") or {},
        },
    }


def list_runs(
    *,
    limit: int = 100,
    offset: int = 0,
    service: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    config_name: str | None = None,
    config_id: str | None = None,
    run_id: str | None = None,
    test_type: str | None = None,
    triggered_by: str | None = None,
    q: str | None = None,
    started_from: str | None = None,
    started_to: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    with _lock:
        rows = _read_json(RUNS_FILE)
    rows.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    from_bound = _day_bound(started_from, end=False)
    to_bound = _day_bound(started_to, end=True)
    matched: list[dict[str, Any]] = []
    rid = (run_id or "").strip()
    for row in rows:
        if rid and str(row.get("id") or "") != rid and not str(row.get("id") or "").startswith(rid):
            continue
        if service and row.get("service") != service:
            continue
        if environment and row.get("environment") != environment:
            continue
        if status and row.get("status") != status:
            continue
        if config_id and str(row.get("config_id") or "") != str(config_id):
            continue
        if config_name and row.get("config_name") != config_name:
            continue
        if test_type and row.get("test_type") != test_type:
            continue
        if triggered_by and row.get("triggered_by") != triggered_by:
            continue
        started = str(row.get("started_at") or "")
        if from_bound and started < from_bound:
            continue
        if to_bound and started > to_bound:
            continue
        if q:
            ql = q.lower()
            blob = " ".join(
                str(row.get(k, "")) for k in ("id", "config_name", "target_url", "service", "error")
            ).lower()
            if ql not in blob:
                continue
        matched.append(row)
    total = len(matched)
    start = max(0, int(offset or 0))
    end = start + max(0, int(limit or 0))
    return matched[start:end], total


def _day_bound(value: str | None, *, end: bool) -> str | None:
    """Normalize YYYY-MM-DD (or full ISO) for started_at comparisons."""
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return raw + ("T23:59:59.999999+00:00" if end else "T00:00:00+00:00")
    return raw


def get_run(run_id: str) -> dict[str, Any] | None:
    with _lock:
        for row in _read_json(RUNS_FILE):
            if row.get("id") == run_id:
                return row
    return None


def save_run(record: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        rows = _read_json(RUNS_FILE)
        if not record.get("id"):
            record["id"] = str(uuid.uuid4())
        if not record.get("started_at"):
            record["started_at"] = _now()
        rows = [r for r in rows if r.get("id") != record["id"]]
        rows.append(record)
        _write_json(RUNS_FILE, rows)
    return record


def update_run(run_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        rows = _read_json(RUNS_FILE)
        for i, row in enumerate(rows):
            if row.get("id") == run_id:
                row.update(patch)
                rows[i] = row
                _write_json(RUNS_FILE, rows)
                return row
    return None


def _hydrate_api_summary_live(
    summary: list[dict[str, Any]],
    *,
    by_api: dict[str, Any],
    last_api_id: str | None,
    total_iters: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for api_row in summary:
        row = dict(api_row)
        aid = str(row.get("api_id") or "")
        calls = int((by_api.get(aid) or {}).get("calls") or row.get("request_count") or 0)
        row["request_count"] = calls
        if aid and last_api_id and aid == str(last_api_id):
            row["live_state"] = "calling"
            row["status"] = "running"
        elif total_iters and calls >= total_iters:
            row["live_state"] = "completed"
            row["status"] = "done"
        elif calls > 0:
            row["live_state"] = "in_progress"
            row["status"] = "running"
        else:
            row["live_state"] = "pending"
            row["status"] = "pending"
        out.append(row)
    return out


def increment_run_progress(
    run_id: str,
    *,
    event: str = "tick",
    total: int | None = None,
    api_count: int | None = None,
    vu: int | None = None,
    api_id: str | None = None,
) -> dict[str, Any] | None:
    """Atomically bump live progress on disk (safe across reload / multi-process)."""
    with _lock:
        rows = _read_json(RUNS_FILE)
        for i, row in enumerate(rows):
            if row.get("id") != run_id:
                continue
            if row.get("status") != "running":
                return {"ok": False, "reason": "not_running"}
            live = dict(row.get("live") or {})
            if total is None:
                total = live.get("total_iterations")
                if total is None:
                    total = ((row.get("payloads_used") or {}).get("bench_run") or {}).get("iterations")
            if api_count is None:
                api_count = live.get("api_count") or row.get("api_count")
            by_api = dict(live.get("by_api") or {})
            if event == "api":
                hits = int(live.get("api_hits") or 0) + 1
                live["api_hits"] = hits
                live["last_api_id"] = api_id
                if api_id:
                    info = dict(by_api.get(str(api_id)) or {})
                    info["calls"] = int(info.get("calls") or 0) + 1
                    info["last_at"] = _now()
                    by_api[str(api_id)] = info
                    live["by_api"] = by_api
                expected = None
                try:
                    if total and api_count:
                        expected = int(total) * int(api_count)
                except (TypeError, ValueError):
                    expected = None
                if expected:
                    live["pct"] = min(99, int(round(100.0 * hits / expected)))
                live["message"] = (
                    f"Calling APIs… {hits}"
                    + (f"/{expected}" if expected else "")
                    + (f" · last {api_id}" if api_id else "")
                )
            elif event == "tick":
                done = int(live.get("completed_iterations") or 0) + 1
                live["completed_iterations"] = done
                live["total_iterations"] = total
                if total:
                    try:
                        live["pct"] = min(99, int(round(100.0 * float(done) / float(total))))
                    except (TypeError, ValueError):
                        pass
                live["message"] = (
                    f"k6 progress — {done}/{total} iterations"
                    if total
                    else f"k6 progress — {done} iterations complete"
                )
            else:
                live["message"] = live.get("message") or "k6 running…"
                live["heartbeat_at"] = _now()
            live["phase"] = "k6"
            if vu is not None:
                live["active_vus"] = vu
            target_iters = 0
            try:
                target_iters = int(total or 0)
            except (TypeError, ValueError):
                target_iters = 0
            summary = list(row.get("api_summary") or [])
            if summary:
                row["api_summary"] = _hydrate_api_summary_live(
                    summary,
                    by_api=by_api,
                    last_api_id=live.get("last_api_id"),
                    total_iters=target_iters,
                )
            row["live"] = live
            row["status"] = "running"
            rows[i] = row
            _write_json(RUNS_FILE, rows)
            return {"ok": True, "live": live, "completed": live.get("completed_iterations"), "total": total}
    return {"ok": False, "reason": "missing"}


def list_configs(
    *,
    service: str | None = None,
    environment: str | None = None,
    audience: str | None = None,
) -> list[dict[str, Any]]:
    with _lock:
        rows = _read_json(CONFIGS_FILE)
    if service:
        rows = [r for r in rows if r.get("service") == service]
    if environment:
        rows = [r for r in rows if r.get("environment") == environment]
    if audience:
        rows = [r for r in rows if (r.get("audience") or "developer") == audience]
    rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return rows


def get_config(config_id: str) -> dict[str, Any] | None:
    with _lock:
        for row in _read_json(CONFIGS_FILE):
            if row.get("id") == config_id:
                return row
    return None


def save_config(record: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        rows = _read_json(CONFIGS_FILE)
        now = _now()
        if not record.get("id"):
            record["id"] = str(uuid.uuid4())
            record.setdefault("created_at", now)
        record["updated_at"] = now
        rows = [r for r in rows if r.get("id") != record["id"]]
        rows.append(record)
        _write_json(CONFIGS_FILE, rows)
    return record


def delete_config(config_id: str) -> bool:
    with _lock:
        rows = _read_json(CONFIGS_FILE)
        kept = [r for r in rows if r.get("id") != config_id]
        if len(kept) == len(rows):
            return False
        _write_json(CONFIGS_FILE, kept)
        return True
