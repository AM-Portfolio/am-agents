from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.acl import AclMiddleware, Caller, seed_bootstrap_keys
from app.api.platform import router as platform_router
from app.config import settings
from app.config_builder import config_from_request, ensure_default_config
from app.dashboard import render_portal
from app.db.engine import init_db, store_mode
from app.grafana_links import grafana_embed_url, grafana_run_url
from app import load_ops
from app.load_runner import (
    get_run_api_index,
    get_run_trace,
    get_run_trace_at,
    list_run_traces,
)
from app.mcp_control import mount_mcp
from app.payload_store import (
    create_payload_set,
    delete_payload,
    ensure_payload_set,
    get_payload,
    get_payload_set,
    list_payload_sets,
    list_payloads,
    save_from_trace,
    save_payload,
    set_active_payload_set,
    upsert_api_in_payload_set,
)
from app.runners import process_registry
from app.run_store import (
    delete_config,
    get_config,
    get_run,
    increment_run_progress,
    list_configs,
    list_runs,
    save_config,
    save_run,
    slim_run_for_list,
    update_run,
)
from app.schemas import (
    PayloadCreateRequest,
    PayloadSetCreateRequest,
    PayloadSetUpsertApiRequest,
    RunExecuteRequest,
    SavePayloadRequest,
    TestConfigIn,
    TestConfigUpdate,
)
from app.services import compare_runs, previous_for_profile
from app.services import execute_svc
from app.trace_store import filter_api_index

app = FastAPI(
    title="SPT Load Test Portal",
    version="1.0.0",
    description="Self-hosted load testing — k6, configs, Grafana metrics, MCP control",
    root_path=settings.root_path.rstrip("/") if settings.root_path else "",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
app.include_router(platform_router)
app.add_middleware(AclMiddleware)
mount_mcp(app)


@app.on_event("startup")
async def startup() -> None:
    if store_mode() != "json":
        init_db()
        try:
            from app.db.migrate_json import migrate_all

            migrate_all()
        except Exception:
            pass
        seed_bootstrap_keys()
        # Orphaned "running" rows from crashed processes / JSON migration
        try:
            from app.run_store import list_runs, update_run

            rows, _ = list_runs(limit=200, status="running")
            for row in rows:
                update_run(
                    str(row["id"]),
                    {
                        "status": "failed",
                        "passed": False,
                        "error": row.get("error") or "stale running state cleared on startup",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "live": {"phase": "error", "message": "cleared on startup"},
                    },
                )
        except Exception:
            pass
    ensure_default_config()


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    prefix = settings.root_path.rstrip("/") if settings.root_path else ""
    return RedirectResponse(url=f"{prefix}/ui")


@app.get("/ui", include_in_schema=False, response_class=HTMLResponse)
async def dashboard_ui() -> HTMLResponse:
    return HTMLResponse(render_portal())


@app.get("/api/runs")
async def api_list_runs(
    service: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    config_name: str | None = None,
    config_id: str | None = None,
    run_id: str | None = None,
    test_type: str | None = None,
    triggered_by: str | None = None,
    q: str | None = None,
    started_from: str | None = Query(None, alias="from"),
    started_to: str | None = Query(None, alias="to"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    runs, total = list_runs(
        limit=limit,
        offset=offset,
        service=service,
        environment=environment,
        status=status,
        config_name=config_name,
        config_id=config_id,
        run_id=run_id,
        test_type=test_type,
        triggered_by=triggered_by,
        q=q,
        started_from=started_from,
        started_to=started_to,
    )
    return {
        "runs": [slim_run_for_list(r) for r in runs],
        "count": len(runs),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/runs/compare")
async def api_compare_runs(
    a: str = Query(..., description="Baseline run id"),
    b: str = Query(..., description="Compare run id"),
) -> dict:
    result = compare_runs(a, b)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result)
    return result


@app.get("/api/runs/{run_id}")
async def api_get_run(run_id: str) -> dict:
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    # Always rebuild so UID/vars track current GRAFANA_* settings (old runs
    # may still point at legacy k6-load-testing).
    row["grafana_url"] = grafana_run_url(
        service=row.get("service"),
        environment=row.get("environment"),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        run_id=run_id,
    )
    row["grafana_embed_url"] = grafana_embed_url(
        service=row.get("service"),
        environment=row.get("environment"),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        run_id=run_id,
    )
    if row.get("api_pass_count") is None or row.get("api_fail_count") is None:
        counts = api_outcome_counts(row.get("api_summary"))
        row.setdefault("api_pass_count", counts["api_pass_count"])
        row.setdefault("api_fail_count", counts["api_fail_count"])
        if not row.get("api_count"):
            row["api_count"] = counts["api_count"]
    return row


@app.post("/api/runs/{run_id}/progress")
async def api_run_progress(run_id: str, body: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """Lightweight callback from k6 for live UI progress (file-backed, reload-safe)."""
    body = body or {}
    result = increment_run_progress(
        run_id,
        event=str(body.get("event") or "tick"),
        total=body.get("total"),
        api_count=body.get("api_count"),
        vu=body.get("vu"),
        api_id=body.get("api_id"),
    )
    if not result:
        return {"ok": False, "reason": "missing"}
    return result


_sample_locks: dict[str, asyncio.Lock] = {}


def _sample_lock(run_id: str) -> asyncio.Lock:
    lock = _sample_locks.get(run_id)
    if lock is None:
        lock = asyncio.Lock()
        _sample_locks[run_id] = lock
    return lock


@app.post("/api/runs/{run_id}/sample")
async def api_run_sample(run_id: str, body: dict[str, Any] = Body(default_factory=dict)) -> dict:
    """Receive one request/response sample from a k6 VU (per-call traces for inspector)."""
    row = get_run(run_id)
    if not row:
        return {"ok": False, "reason": "missing"}
    if not body.get("api_id"):
        return {"ok": False, "reason": "no_api_id"}
    art_dir = Path(settings.data_dir) / "artifacts" / run_id
    art_dir.mkdir(parents=True, exist_ok=True)
    path = art_dir / "traces.json"
    async with _sample_lock(run_id):
        traces: list[dict[str, Any]] = []
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    traces = data
            except Exception:
                traces = []
        if len(traces) >= settings.trace_max_calls:
            return {"ok": True, "api_id": str(body.get("api_id")), "count": len(traces), "truncated": True}
        aid = str(body.get("api_id"))
        sample = dict(body)
        # Server assigns monotonic call_index (k6 VUs have separate JS heaps)
        sample["call_index"] = len(traces) + 1
        traces.append(sample)
        path.write_text(json.dumps(traces, indent=2, default=str), encoding="utf-8")
        # Reflect latest HTTP status into live api_summary when present
        api_summary = list(row.get("api_summary") or [])
        for api_row in api_summary:
            if str(api_row.get("api_id")) == aid:
                api_row["status"] = (sample.get("response") or {}).get("status")
                api_row["trace_available"] = True
                if sample.get("timings"):
                    api_row["duration_ms"] = (sample.get("timings") or {}).get("duration_ms")
                break
        if api_summary:
            update_run(run_id, {"api_summary": api_summary})
        return {"ok": True, "api_id": aid, "count": len(traces)}


@app.get("/api/runs/{run_id}/apis")
async def api_run_apis(
    run_id: str,
    failed_only: bool = False,
    q: str | None = None,
    limit: int = Query(500, le=1000),
    offset: int = 0,
) -> dict:
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    apis = get_run_api_index(run_id) or row.get("api_summary") or []
    filtered, total = filter_api_index(apis, failed_only=failed_only, q=q, limit=limit, offset=offset)
    return {"run_id": run_id, "apis": filtered, "count": len(filtered), "total": total}


@app.get("/api/runs/{run_id}/traces")
async def api_run_traces(
    run_id: str,
    failed_only: bool = False,
    api_id: str | None = None,
    limit: int = Query(500, le=1000),
    offset: int = 0,
) -> dict:
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    traces, total = list_run_traces(
        run_id, api_id=api_id, failed_only=failed_only, limit=limit, offset=offset
    )
    return {"run_id": run_id, "traces": traces, "count": len(traces), "total": total}


@app.get("/api/runs/{run_id}/traces/{index}")
async def api_run_trace_at_index(run_id: str, index: int) -> dict:
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    trace = get_run_trace_at(run_id, index, redact=True)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {"run_id": run_id, "index": index, "trace": trace}


@app.get("/api/runs/{run_id}/apis/{api_id}/trace")
async def api_run_api_trace(run_id: str, api_id: str) -> dict:
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    trace = get_run_trace(run_id, api_id, redact=True)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found for this API")
    return {"run_id": run_id, "api_id": api_id, "trace": trace}


@app.post("/api/runs/{run_id}/apis/{api_id}/save-payload")
async def api_save_payload_from_run(run_id: str, api_id: str, body: SavePayloadRequest | None = None) -> dict:
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    name = (body.name if body else None) or "default"
    service = (body.service if body else None) or row.get("service")
    try:
        saved = save_from_trace(run_id, api_id, name=name, service=service)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return saved


@app.get("/api/payloads")
async def api_list_payloads(
    service: str | None = None,
    api_id: str | None = None,
) -> dict:
    rows = list_payloads(service=service, api_id=api_id)
    return {"payloads": rows, "count": len(rows)}


@app.get("/api/payloads/{service}/{api_id}")
async def api_list_payloads_for_api(service: str, api_id: str) -> dict:
    rows = list_payloads(service=service, api_id=api_id)
    return {"service": service, "api_id": api_id, "payloads": rows, "count": len(rows)}


@app.get("/api/payloads/{service}/{api_id}/{name}")
async def api_get_payload(
    service: str,
    api_id: str,
    name: str,
    version: int | None = None,
) -> dict:
    row = get_payload(service, api_id, name, version)
    if not row:
        raise HTTPException(status_code=404, detail="Payload not found")
    return row


@app.post("/api/payloads")
async def api_create_payload(body: PayloadCreateRequest) -> dict:
    saved = save_payload(
        {
            "service": body.service,
            "api_id": body.api_id,
            "name": body.name,
            "request": body.request,
            "response": body.response,
            "meta": body.meta,
            "source_run_id": body.source_run_id,
        },
        bump=body.bump,
    )
    payload_set = None
    if body.into_set:
        payload_set = upsert_api_in_payload_set(
            body.service,
            body.api_id,
            version=body.set_version,
            request=body.request,
            response=body.response,
            meta=body.meta,
            name=body.name,
            bump_set=body.bump_set,
        )
    return {"payload": saved, "payload_set": payload_set}


@app.get("/api/payload-sets")
async def api_list_payload_sets(service: str = Query(...)) -> dict:
    return list_payload_sets(service)


@app.get("/api/payload-sets/{service}")
async def api_list_payload_sets_path(service: str) -> dict:
    return list_payload_sets(service)


@app.get("/api/payload-sets/{service}/{version}")
async def api_get_payload_set(service: str, version: int) -> dict:
    row = get_payload_set(service, version)
    if not row:
        raise HTTPException(status_code=404, detail="Payload set not found")
    return row


@app.post("/api/payload-sets")
async def api_create_payload_set(body: PayloadSetCreateRequest) -> dict:
    return create_payload_set(
        body.service,
        label=body.label,
        clone_from=body.clone_from,
        make_active=body.make_active,
    )


@app.post("/api/payload-sets/{service}/ensure")
async def api_ensure_payload_set(service: str, label: str = "working") -> dict:
    return ensure_payload_set(service, label=label)


@app.post("/api/payload-sets/{service}/{version}/activate")
async def api_activate_payload_set(service: str, version: int) -> dict:
    try:
        return set_active_payload_set(service, version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/payload-sets/{service}/apis/{api_id}")
async def api_upsert_payload_set_api(
    service: str,
    api_id: str,
    body: PayloadSetUpsertApiRequest,
) -> dict:
    try:
        return upsert_api_in_payload_set(
            service,
            api_id,
            version=body.version,
            request=body.request,
            response=body.response,
            meta=body.meta,
            name=body.name,
            bump_set=body.bump_set,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/payloads/{service}/{api_id}/{name}/{version}")
async def api_delete_payload(service: str, api_id: str, name: str, version: int) -> dict:
    if not delete_payload(service, api_id, name, version):
        raise HTTPException(status_code=404, detail="Payload not found")
    return {"deleted": True, "service": service, "api_id": api_id, "name": name, "version": version}


@app.post("/api/runs/execute")
async def api_execute_run(body: RunExecuteRequest, request: Request) -> dict:
    caller = getattr(request.state, "spt_caller", None) or Caller(role="developer")
    idem = (request.headers.get("idempotency-key") or "").strip() or None
    return await execute_svc.execute_run(body, caller=caller, idempotency_key=idem)


@app.get("/api/runs/{run_id}/baseline")
async def api_run_baseline(run_id: str) -> dict:
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    prev = previous_for_profile(str(row.get("config_id") or ""), exclude_run_id=run_id)
    if not prev:
        return {"ok": False, "message": "no previous run for profile"}
    cmp = compare_runs(str(prev.get("id")), run_id)
    return {"ok": True, "previous": prev, "compare": cmp}


@app.post("/api/runs/{run_id}/stop")
async def api_stop_run(run_id: str) -> dict:
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    if row.get("status") != "running":
        return {"ok": True, "status": row.get("status"), "message": "already finished"}
    stop_result = process_registry.request_stop(run_id)
    update_run(
        run_id,
        {
            "status": "cancelled",
            "passed": False,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error": "stopped by user",
            "live": {"phase": "cancelled", "message": "Stopped by user"},
        },
    )
    return {"ok": True, "status": "cancelled", "stop": stop_result}


def _list_profiles_payload(
    service: str | None = None,
    environment: str | None = None,
    audience: str | None = None,
) -> dict:
    configs = list_configs(service=service, environment=environment, audience=audience)
    if not configs:
        configs = [ensure_default_config()]
        configs = list_configs(service=service, environment=environment, audience=audience) or configs
    return {"configs": configs, "profiles": configs, "count": len(configs)}


@app.get("/api/configs")
async def api_list_configs(
    service: str | None = None,
    environment: str | None = None,
    audience: str | None = None,
) -> dict:
    return _list_profiles_payload(service, environment, audience)


@app.get("/api/profiles")
async def api_list_profiles(
    service: str | None = None,
    environment: str | None = None,
    audience: str | None = None,
) -> dict:
    return _list_profiles_payload(service, environment, audience)


@app.get("/api/profiles/default")
async def api_default_profile() -> dict:
    return ensure_default_config()


@app.get("/api/profiles/{config_id}")
async def api_get_profile(config_id: str) -> dict:
    row = get_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return row


@app.post("/api/profiles")
async def api_create_profile(body: TestConfigIn) -> dict:
    return save_config(config_from_request(body))


@app.put("/api/profiles/{config_id}")
async def api_update_profile(config_id: str, body: TestConfigUpdate) -> dict:
    return await api_update_config(config_id, body)


@app.delete("/api/profiles/{config_id}")
async def api_delete_profile(config_id: str) -> dict:
    if not delete_config(config_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"deleted": config_id}


@app.get("/api/configs/default")
async def api_default_config() -> dict:
    return ensure_default_config()


@app.get("/api/configs/{config_id}")
async def api_get_config(config_id: str) -> dict:
    row = get_config(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="Config not found")
    return row


@app.post("/api/configs")
async def api_create_config(body: TestConfigIn) -> dict:
    return save_config(config_from_request(body))


@app.put("/api/configs/{config_id}")
async def api_update_config(config_id: str, body: TestConfigUpdate) -> dict:
    existing = get_config(config_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Config not found")
    patch = body.model_dump(exclude_unset=True)
    payloads_patch = None
    if body.payloads is not None:
        payloads_patch = body.payloads.model_dump(exclude_unset=True)
        patch.pop("payloads", None)
    scripts_patch = patch.pop("scripts", None)
    merged = {**existing, **patch}
    if payloads_patch is not None:
        existing_payloads = dict(existing.get("payloads") or {})
        # Nested merge for auth_env / bench_run so partial updates do not wipe keys
        if isinstance(payloads_patch.get("auth_env"), dict):
            payloads_patch["auth_env"] = {
                **(existing_payloads.get("auth_env") or {}),
                **payloads_patch["auth_env"],
            }
        if isinstance(payloads_patch.get("bench_run"), dict):
            payloads_patch["bench_run"] = {
                **(existing_payloads.get("bench_run") or {}),
                **payloads_patch["bench_run"],
            }
        merged["payloads"] = {**existing_payloads, **payloads_patch}
        if "payload_set_version" in payloads_patch and payloads_patch["payload_set_version"] is not None:
            merged["payload_set_version"] = payloads_patch["payload_set_version"]
    if "payload_set_version" in patch:
        merged["payload_set_version"] = patch["payload_set_version"]
        payloads = dict(merged.get("payloads") or {})
        payloads["payload_set_version"] = patch["payload_set_version"]
        merged["payloads"] = payloads
    if scripts_patch is not None:
        merged["scripts"] = {**existing.get("scripts", {}), **scripts_patch}
    merged["id"] = config_id
    return save_config(merged)


@app.delete("/api/configs/{config_id}")
async def api_delete_config(config_id: str) -> dict:
    if not delete_config(config_id):
        raise HTTPException(status_code=404, detail="Config not found")
    return {"deleted": config_id}


@app.post("/api/runs/{run_id}/save-config")
async def api_save_config_from_run(run_id: str, name: str | None = None) -> dict:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    snap = run.get("config_snapshot") or {}
    payloads = run.get("payloads_used") or snap.get("payloads") or {}
    cfg = save_config(
        {
            "name": name or f"from-run-{run_id[:8]}",
            "description": f"Saved from run {run_id}",
            "environment": run.get("environment") or settings.default_environment,
            "service": run.get("service") or "am-analysis",
            "test_type": run.get("test_type") or "k6",
            "run_profile": run.get("run_profile") or snap.get("run_profile") or "load",
            "audience": snap.get("audience") or "developer",
            "payload_set_version": snap.get("payload_set_version")
            or (payloads.get("payload_set_version") if isinstance(payloads, dict) else None),
            "openapi_version": run.get("openapi_version"),
            "target_url": run.get("target_url"),
            "payloads": payloads,
            "scripts": snap.get("scripts") or {},
        }
    )
    return cfg

@app.get("/api/runs/{run_id}/export")
async def api_export_run(run_id: str) -> dict:
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


@app.post("/smoke")
async def smoke() -> dict:
    cfg = ensure_default_config()
    record = await load_ops.run_test_from_config(cfg, triggered_by="manual")
    save_run(record)
    return record
