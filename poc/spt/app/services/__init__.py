"""Domain services shared by REST and MCP."""

from __future__ import annotations

import time
from typing import Any

from app import load_ops
from app.catalog_loader import (
    default_target_for_service,
    list_registered_services,
    load_catalog,
    load_service_apis,
    openapi_versions_by_env,
    reachable_target_for_service,
)
from app.config import settings
from app.config_builder import ensure_default_config
from app.db.engine import db_health, store_mode
from app.load_runner import get_run_trace_at, list_run_traces
from app.payload_store import (
    get_payload_set,
    list_payload_sets,
    list_payloads,
    save_payload,
    set_active_payload_set,
)
from app.run_store import (
    count_running,
    get_config,
    get_run,
    list_configs,
    list_runs,
    slim_run_for_list,
)


def health() -> dict[str, Any]:
    t0 = time.perf_counter()
    rows, total = list_runs(limit=10, offset=0)
    list_ms = (time.perf_counter() - t0) * 1000
    return {
        "status": "ok",
        "service": settings.app_name,
        "store": store_mode(),
        "db": db_health(),
        "running": count_running(),
        "max_concurrent_runs": settings.spt_max_concurrent_runs,
        "latency": {
            "list_10_runs_ms": round(list_ms, 2),
            "slo_list_ms": 50,
            "list_ok": list_ms < 50,
        },
        "runs_sample": len(rows),
        "runs_total": total,
    }


def list_services() -> dict[str, Any]:
    services = list_registered_services()
    return {"services": services, "count": len(services), "catalog": load_catalog()}


def list_apis(service: str, environment: str | None = None) -> dict[str, Any]:
    env = environment or settings.default_environment
    data = load_service_apis(service, env)
    return {
        "service": service,
        "environment": env,
        "apis": data.get("apis") or [],
        "count": len(data.get("apis") or []),
        "target_url": reachable_target_for_service(service, env),
        "openapi_version": data.get("openapi_version"),
    }


def resolve_target(service: str, environment: str | None = None) -> dict[str, Any]:
    env = environment or settings.default_environment
    return {
        "service": service,
        "environment": env,
        "target_url": reachable_target_for_service(service, env),
        "default_target": default_target_for_service(service, env),
    }


def openapi_versions(service: str) -> dict[str, Any]:
    versions = openapi_versions_by_env(service)
    return {"service": service, "environments": versions, "count": len(versions)}


def profiles_list(
    *, service: str | None = None, environment: str | None = None, audience: str | None = None
) -> list[dict[str, Any]]:
    return list_configs(service=service, environment=environment, audience=audience)


def profile_get(config_id: str) -> dict[str, Any] | None:
    return get_config(config_id)


def ensure_defaults() -> dict[str, Any]:
    return ensure_default_config()


def runs_list(**kwargs: Any) -> dict[str, Any]:
    rows, total = list_runs(**kwargs)
    return {"runs": [slim_run_for_list(r) for r in rows], "total": total, "count": len(rows)}


def run_get(run_id: str) -> dict[str, Any] | None:
    return get_run(run_id)


def run_live(run_id: str) -> dict[str, Any] | None:
    row = get_run(run_id)
    if not row:
        return None
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "live": row.get("live") or {},
        "passed": row.get("passed"),
        "error": row.get("error"),
        "finished_at": row.get("finished_at"),
    }


def traces_list(run_id: str, *, limit: int = 50, offset: int = 0, api_id: str | None = None) -> dict:
    return list_run_traces(run_id, limit=limit, offset=offset, api_id=api_id)


def trace_get(run_id: str, index: int) -> dict | None:
    return get_run_trace_at(run_id, index)


def compare_runs(run_a: str, run_b: str) -> dict[str, Any]:
    a = get_run(run_a)
    b = get_run(run_b)
    if not a or not b:
        missing = []
        if not a:
            missing.append(run_a)
        if not b:
            missing.append(run_b)
        return {"ok": False, "missing": missing}
    def snap(r: dict) -> dict:
        return {
            "id": r.get("id"),
            "status": r.get("status"),
            "passed": r.get("passed"),
            "config_name": r.get("config_name"),
            "service": r.get("service"),
            "environment": r.get("environment"),
            "vus": r.get("vus"),
            "iterations": r.get("iterations"),
            "duration": r.get("duration"),
            "fail_pct": r.get("fail_pct"),
            "p90_ms": r.get("p90_ms"),
            "rps": r.get("rps"),
            "api_pass_count": r.get("api_pass_count"),
            "api_fail_count": r.get("api_fail_count"),
            "api_count": r.get("api_count"),
            "started_at": r.get("started_at"),
        }
    sa, sb = snap(a), snap(b)
    deltas = {}
    for k in ("fail_pct", "p90_ms", "rps", "api_pass_count", "api_fail_count", "vus", "iterations"):
        va, vb = sa.get(k), sb.get(k)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            deltas[k] = vb - va
    return {"ok": True, "a": sa, "b": sb, "deltas_b_minus_a": deltas}


def previous_for_profile(config_id: str, *, exclude_run_id: str | None = None) -> dict | None:
    rows, _ = list_runs(limit=5, offset=0, config_id=config_id)
    for r in rows:
        if exclude_run_id and r.get("id") == exclude_run_id:
            continue
        if r.get("status") == "running":
            continue
        return slim_run_for_list(r)
    return None


def payload_sets(service: str) -> dict:
    return list_payload_sets(service)


def payload_set_get(service: str, version: int | None = None) -> dict | None:
    return get_payload_set(service, version)


def activate_payload_set(service: str, version: int) -> dict:
    return set_active_payload_set(service, version)


def payloads_list(*, service: str | None = None, api_id: str | None = None) -> list:
    return list_payloads(service=service, api_id=api_id)


def upsert_payload(record: dict) -> dict:
    return save_payload(record)


async def platform_health() -> dict:
    return await load_ops.platform_health()
