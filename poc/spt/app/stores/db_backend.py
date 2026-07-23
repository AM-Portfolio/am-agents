from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.engine import get_session
from app.db.models import IdempotencyKeyRow, ProfileRow, RunDetailRow, RunLiveRow, RunRow
from app.stores import json_backend as jb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hot_from_record(record: dict[str, Any]) -> dict[str, Any]:
    payloads = record.get("payloads_used") or {}
    bench = payloads.get("bench_run") or {}
    auth = payloads.get("auth_env") or {}
    metrics = record.get("metrics_summary") or {}
    counts = {
        "api_pass_count": record.get("api_pass_count"),
        "api_fail_count": record.get("api_fail_count"),
        "api_count": record.get("api_count"),
    }
    if counts["api_pass_count"] is None or counts["api_fail_count"] is None:
        derived = jb.api_outcome_counts(record.get("api_summary"))
        if counts["api_pass_count"] is None:
            counts["api_pass_count"] = derived["api_pass_count"]
        if counts["api_fail_count"] is None:
            counts["api_fail_count"] = derived["api_fail_count"]
        if not counts["api_count"]:
            counts["api_count"] = derived["api_count"] or record.get("api_count")
    err = record.get("error")
    err_short = record.get("error_short")
    if not err_short and err:
        err_short = str(err)[:512]
    snap = record.get("config_snapshot") or {}
    audience = record.get("audience") or snap.get("audience")
    return {
        "id": record.get("id"),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at"),
        "status": record.get("status"),
        "passed": record.get("passed"),
        "runner": record.get("runner"),
        "run_profile": record.get("run_profile"),
        "config_id": record.get("config_id"),
        "config_name": record.get("config_name"),
        "service": record.get("service"),
        "environment": record.get("environment"),
        "openapi_version": record.get("openapi_version"),
        "test_type": record.get("test_type"),
        "audience": audience,
        "triggered_by": record.get("triggered_by"),
        "caller_role": record.get("caller_role"),
        "caller_key_id": record.get("caller_key_id"),
        "target_url": record.get("target_url"),
        "api_count": counts["api_count"],
        "api_pass_count": counts["api_pass_count"],
        "api_fail_count": counts["api_fail_count"],
        "vus": record.get("vus") if record.get("vus") is not None else bench.get("vus"),
        "iterations": record.get("iterations")
        if record.get("iterations") is not None
        else bench.get("iterations"),
        "duration": record.get("duration") if record.get("duration") is not None else bench.get("duration"),
        "fail_pct": record.get("fail_pct")
        if record.get("fail_pct") is not None
        else metrics.get("http_req_failed"),
        "p90_ms": record.get("p90_ms")
        if record.get("p90_ms") is not None
        else (metrics.get("http_req_duration") or {}).get("p90")
        if isinstance(metrics.get("http_req_duration"), dict)
        else metrics.get("p90_ms"),
        "rps": record.get("rps") if record.get("rps") is not None else metrics.get("http_reqs"),
        "auth_username": record.get("auth_username") or auth.get("username"),
        "error_short": err_short,
        "grafana_url": record.get("grafana_url"),
        "error": err,
    }


_KNOWN_HOT = {
    "id",
    "started_at",
    "finished_at",
    "status",
    "passed",
    "runner",
    "run_profile",
    "config_id",
    "config_name",
    "service",
    "environment",
    "openapi_version",
    "test_type",
    "audience",
    "triggered_by",
    "caller_role",
    "caller_key_id",
    "target_url",
    "api_count",
    "api_pass_count",
    "api_fail_count",
    "vus",
    "iterations",
    "duration",
    "fail_pct",
    "p90_ms",
    "rps",
    "auth_username",
    "error_short",
    "grafana_url",
    "error",
}

_DETAIL_KEYS = {
    "payloads_used",
    "metrics_summary",
    "api_summary",
    "steps",
    "config_snapshot",
    "api_ids",
}


def _extra_from_record(record: dict[str, Any]) -> dict[str, Any]:
    skip = _KNOWN_HOT | _DETAIL_KEYS | {"live", "id"}
    return {k: v for k, v in record.items() if k not in skip}


def _row_to_dict(row: RunRow, *, include_detail: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "status": row.status,
        "passed": row.passed,
        "runner": row.runner,
        "run_profile": row.run_profile,
        "config_id": row.config_id,
        "config_name": row.config_name,
        "service": row.service,
        "environment": row.environment,
        "openapi_version": row.openapi_version,
        "test_type": row.test_type,
        "audience": row.audience,
        "triggered_by": row.triggered_by,
        "caller_role": row.caller_role,
        "caller_key_id": row.caller_key_id,
        "target_url": row.target_url,
        "api_count": row.api_count,
        "api_pass_count": row.api_pass_count,
        "api_fail_count": row.api_fail_count,
        "vus": row.vus,
        "iterations": row.iterations,
        "duration": row.duration,
        "fail_pct": row.fail_pct,
        "p90_ms": row.p90_ms,
        "rps": row.rps,
        "auth_username": row.auth_username,
        "error_short": row.error_short,
        "grafana_url": row.grafana_url,
        "error": row.error,
    }
    if row.live and row.live.live is not None:
        out["live"] = row.live.live
    if include_detail and row.detail:
        d = row.detail
        if d.payloads_used is not None:
            out["payloads_used"] = d.payloads_used
        if d.metrics_summary is not None:
            out["metrics_summary"] = d.metrics_summary
        if d.api_summary is not None:
            out["api_summary"] = d.api_summary
        if d.steps is not None:
            out["steps"] = d.steps
        if d.config_snapshot is not None:
            out["config_snapshot"] = d.config_snapshot
        if d.api_ids is not None:
            out["api_ids"] = d.api_ids
        if d.extra:
            out.update(d.extra)
    return out


def _apply_hot(row: RunRow, hot: dict[str, Any]) -> None:
    for k, v in hot.items():
        if k == "id":
            continue
        if hasattr(row, k):
            setattr(row, k, v)


def _upsert_run(session: Session, record: dict[str, Any]) -> dict[str, Any]:
    if not record.get("id"):
        record["id"] = str(uuid.uuid4())
    if not record.get("started_at"):
        record["started_at"] = _now()
    hot = _hot_from_record(record)
    rid = str(hot["id"])
    row = session.get(RunRow, rid)
    if row is None:
        row = RunRow(id=rid)
        session.add(row)
    _apply_hot(row, hot)

    detail = session.get(RunDetailRow, rid)
    if detail is None:
        detail = RunDetailRow(run_id=rid)
        session.add(detail)
    detail.payloads_used = record.get("payloads_used")
    detail.metrics_summary = record.get("metrics_summary")
    detail.api_summary = record.get("api_summary")
    detail.steps = record.get("steps")
    detail.config_snapshot = record.get("config_snapshot")
    detail.api_ids = record.get("api_ids")
    detail.extra = _extra_from_record(record) or None

    if "live" in record:
        live = session.get(RunLiveRow, rid)
        if live is None:
            live = RunLiveRow(run_id=rid)
            session.add(live)
        live.live = record.get("live")
        live.updated_at = datetime.now(timezone.utc)

    session.flush()
    return _row_to_dict(row, include_detail=True)


def save_run(record: dict[str, Any]) -> dict[str, Any]:
    with get_session() as session:
        return _upsert_run(session, dict(record))


def update_run(run_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.get(RunRow, run_id)
        if not row:
            return None
        current = _row_to_dict(row, include_detail=True)
        current.update(patch)
        return _upsert_run(session, current)


def get_run(run_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.get(RunRow, run_id)
        if not row:
            return None
        return _row_to_dict(row, include_detail=True)


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
    with get_session() as session:
        filters = []
        from_bound = jb._day_bound(started_from, end=False)
        to_bound = jb._day_bound(started_to, end=True)
        if run_id:
            rid = run_id.strip()
            filters.append(or_(RunRow.id == rid, RunRow.id.startswith(rid)))
        if service:
            filters.append(RunRow.service == service)
        if environment:
            filters.append(RunRow.environment == environment)
        if status:
            filters.append(RunRow.status == status)
        if config_id:
            filters.append(RunRow.config_id == str(config_id))
        if config_name:
            filters.append(RunRow.config_name == config_name)
        if test_type:
            filters.append(RunRow.test_type == test_type)
        if triggered_by:
            filters.append(RunRow.triggered_by == triggered_by)
        if from_bound:
            filters.append(RunRow.started_at >= from_bound)
        if to_bound:
            filters.append(RunRow.started_at <= to_bound)
        if q:
            ql = f"%{q.lower()}%"
            filters.append(
                or_(
                    func.lower(RunRow.id).like(ql),
                    func.lower(func.coalesce(RunRow.config_name, "")).like(ql),
                    func.lower(func.coalesce(RunRow.target_url, "")).like(ql),
                    func.lower(func.coalesce(RunRow.service, "")).like(ql),
                    func.lower(func.coalesce(RunRow.error, "")).like(ql),
                )
            )
        where = and_(*filters) if filters else True
        total = session.scalar(select(func.count()).select_from(RunRow).where(where)) or 0
        stmt = (
            select(RunRow)
            .where(where)
            .order_by(RunRow.started_at.desc())
            .offset(max(0, int(offset or 0)))
            .limit(max(0, int(limit or 0)))
        )
        rows = session.scalars(stmt).all()
        # Attach live cheaply for list (optional slim)
        out = []
        for row in rows:
            d = _row_to_dict(row, include_detail=False)
            if row.live and row.live.live is not None:
                d["live"] = row.live.live
            # Minimal payloads for slim_run_for_list
            d["payloads_used"] = {
                "bench_run": {
                    "vus": row.vus,
                    "iterations": row.iterations,
                    "duration": row.duration,
                },
                "auth_env": {"username": row.auth_username} if row.auth_username else {},
            }
            out.append(d)
        return out, int(total)


def increment_run_progress(
    run_id: str,
    *,
    event: str = "tick",
    total: int | None = None,
    api_count: int | None = None,
    vu: int | None = None,
    api_id: str | None = None,
) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.get(RunRow, run_id)
        if not row:
            return {"ok": False, "reason": "missing"}
        if row.status != "running":
            return {"ok": False, "reason": "not_running"}
        live_row = session.get(RunLiveRow, run_id)
        if live_row is None:
            live_row = RunLiveRow(run_id=run_id, live={})
            session.add(live_row)
        live = dict(live_row.live or {})
        detail = session.get(RunDetailRow, run_id)
        if total is None:
            total = live.get("total_iterations")
            if total is None and detail and detail.payloads_used:
                total = ((detail.payloads_used or {}).get("bench_run") or {}).get("iterations")
        if api_count is None:
            api_count = live.get("api_count") or row.api_count
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
        if detail and detail.api_summary:
            detail.api_summary = jb._hydrate_api_summary_live(
                list(detail.api_summary or []),
                by_api=by_api,
                last_api_id=live.get("last_api_id"),
                total_iters=target_iters,
            )
        live_row.live = live
        live_row.updated_at = datetime.now(timezone.utc)
        row.status = "running"
        session.flush()
        return {"ok": True, "live": live, "completed": live.get("completed_iterations"), "total": total}


def count_running() -> int:
    with get_session() as session:
        return int(
            session.scalar(select(func.count()).select_from(RunRow).where(RunRow.status == "running"))
            or 0
        )


# --- profiles ---


def _profile_to_dict(row: ProfileRow) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "name": row.name,
        "service": row.service,
        "environment": row.environment,
        "audience": row.audience or "developer",
        "openapi_version": row.openapi_version,
        "test_type": row.test_type,
        "target_url": row.target_url,
        "run_profile": row.run_profile,
        "payload_set_version": row.payload_set_version,
        "selected_api_ids": row.selected_api_ids,
        "payloads": row.payloads or {},
        "scripts": row.scripts or {},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if row.extra:
        for k, v in row.extra.items():
            if k not in out:
                out[k] = v
    return out


def _upsert_profile(session: Session, record: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    if not record.get("id"):
        record["id"] = str(uuid.uuid4())
        record.setdefault("created_at", now)
    record["updated_at"] = now
    rid = str(record["id"])
    row = session.get(ProfileRow, rid)
    if row is None:
        row = ProfileRow(id=rid)
        session.add(row)
    known = {
        "name",
        "service",
        "environment",
        "audience",
        "openapi_version",
        "test_type",
        "target_url",
        "run_profile",
        "payload_set_version",
        "selected_api_ids",
        "payloads",
        "scripts",
        "created_at",
        "updated_at",
    }
    for k in known:
        if k in record:
            setattr(row, k, record.get(k))
    extra = {k: v for k, v in record.items() if k not in known and k != "id"}
    row.extra = extra or None
    session.flush()
    return _profile_to_dict(row)


def list_configs(
    *,
    service: str | None = None,
    environment: str | None = None,
    audience: str | None = None,
) -> list[dict[str, Any]]:
    with get_session() as session:
        filters = []
        if service:
            filters.append(ProfileRow.service == service)
        if environment:
            filters.append(ProfileRow.environment == environment)
        if audience:
            filters.append(func.coalesce(ProfileRow.audience, "developer") == audience)
        where = and_(*filters) if filters else True
        rows = session.scalars(
            select(ProfileRow).where(where).order_by(ProfileRow.updated_at.desc())
        ).all()
        return [_profile_to_dict(r) for r in rows]


def get_config(config_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.get(ProfileRow, config_id)
        return _profile_to_dict(row) if row else None


def save_config(record: dict[str, Any]) -> dict[str, Any]:
    with get_session() as session:
        return _upsert_profile(session, dict(record))


def delete_config(config_id: str) -> bool:
    with get_session() as session:
        row = session.get(ProfileRow, config_id)
        if not row:
            return False
        session.delete(row)
        return True


def get_idempotency(key: str) -> str | None:
    with get_session() as session:
        row = session.scalar(select(IdempotencyKeyRow).where(IdempotencyKeyRow.key == key))
        return row.run_id if row else None


def put_idempotency(key: str, run_id: str) -> None:
    with get_session() as session:
        existing = session.scalar(select(IdempotencyKeyRow).where(IdempotencyKeyRow.key == key))
        if existing:
            return
        session.add(IdempotencyKeyRow(key=key, run_id=run_id, created_at=_now()))
