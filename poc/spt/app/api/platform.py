from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from app import load_ops
from app.assets import scripts_bundle
from app.catalog_loader import (
    default_target_for_service,
    list_registered_services,
    load_catalog,
    load_openapi_document,
    load_registration,
    load_service_apis,
    openapi_versions_by_env,
    platform_bearer_token,
    proxy_try_request,
    reachable_target_for_service,
)
from app.config import settings
from app.openapi_overlay import load_overlay, merge_effective_document
from app.payload_pipeline import build_payload, ensure_working_payload
from app.schemas import PayloadBuildRequest, PayloadEnsureRequest

router = APIRouter(tags=["platform"])

_TRY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


@router.get("/health")
async def health() -> dict:
    from app.services import health as svc_health

    return svc_health()


@router.get("/ready")
async def ready() -> dict:
    h = await load_ops.platform_health()
    from app.db.engine import db_health, store_mode

    return {"status": "ready", "platform": h, "store": store_mode(), "db": db_health()}


@router.get("/api/catalog")
async def api_catalog() -> dict:
    return load_catalog()


@router.get("/api/catalog/registrations")
async def api_catalog_registrations() -> dict:
    """Configured SPT registrations (spt.yaml) for Specs UI."""
    services = list_registered_services()
    return {"services": services, "count": len(services)}


@router.get("/api/catalog/{service}/apis")
async def api_service_apis(
    service: str,
    environment: str | None = Query(default=None, description="dev|preprod|prod — picks targets[env]"),
) -> dict:
    env = environment or settings.default_environment
    data = load_service_apis(service, env)
    reg = load_registration(service)
    target = reachable_target_for_service(service, env)
    # target_url last so registration/baked payloads cannot overwrite the reachable URL
    return {
        "service": service,
        "environment": env,
        "runtime": (reg or {}).get("runtime") or data.get("runtime"),
        "openapi_version": data.get("openapi_version"),
        **data,
        "target_url": target,
        "count": len(data.get("apis") or []),
    }


@router.get("/api/catalog/{service}/target")
async def api_service_target(
    service: str,
    environment: str | None = Query(default=None, description="dev|preprod|prod"),
) -> dict:
    """Resolve browser/k6-reachable base URL for service+env (public_* outside cluster)."""
    env = environment or settings.default_environment
    reg = load_registration(service) or {}
    targets = reg.get("targets") if isinstance(reg.get("targets"), dict) else {}
    target = reachable_target_for_service(service, env)
    return {
        "service": service,
        "environment": env,
        "target_url": target,
        "targets": targets,
        "public_key": f"public_{env}",
        "cluster_key": env,
    }


@router.get("/api/catalog/{service}/openapi/document")
async def api_service_openapi_document(
    service: str,
    environment: str | None = Query(default=None),
    effective: bool = Query(default=False, description="Merge SPT overlay examples into document"),
):
    """Raw OpenAPI JSON proxied by SPT (browser-reachable; cluster DNS is not)."""
    meta = load_openapi_document(service, environment)
    if not meta.get("ok") or not isinstance(meta.get("document"), dict):
        raise HTTPException(
            status_code=502,
            detail=meta.get("error") or f"OpenAPI unavailable for {service}",
        )
    doc = meta["document"]
    env = str(meta.get("environment") or environment or settings.default_environment)
    if effective:
        doc, _overlay = merge_effective_document(doc, service, env)
    return JSONResponse(
        content=doc,
        headers={
            "X-SPT-OpenAPI-Source": str(meta.get("openapi_url") or ""),
            "X-SPT-Service": service,
            "X-SPT-Environment": env,
            "X-SPT-OpenAPI-Effective": "1" if effective else "0",
        },
    )


@router.get("/api/catalog/{service}/openapi/effective")
async def api_service_openapi_effective(
    service: str,
    environment: str | None = Query(default=None),
) -> dict:
    """Live OpenAPI merged with SPT-local overlay (examples from ensure-working / sets)."""
    env = environment or settings.default_environment
    meta = load_openapi_document(service, env)
    if not meta.get("ok") or not isinstance(meta.get("document"), dict):
        raise HTTPException(
            status_code=502,
            detail=meta.get("error") or f"OpenAPI unavailable for {service}",
        )
    doc, overlay = merge_effective_document(meta["document"], service, env)
    return {
        "service": service,
        "environment": env,
        "ok": True,
        "version": meta.get("version"),
        "openapi_url": meta.get("openapi_url"),
        "overlay": {
            "updated_at": overlay.get("updated_at"),
            "operation_count": len(overlay.get("operations") or {}),
        },
        "document": doc,
    }


@router.get("/api/catalog/{service}/openapi")
async def api_service_openapi(
    service: str,
    environment: str | None = Query(default=None),
    include_document: bool = Query(default=True, description="Include full OpenAPI JSON"),
    effective: bool = Query(default=False, description="Merge SPT overlay into document"),
) -> dict:
    """Live OpenAPI document + registration config for Swagger-style Specs UI."""
    meta = load_openapi_document(service, environment)
    if include_document and effective and isinstance(meta.get("document"), dict):
        env = str(meta.get("environment") or environment or settings.default_environment)
        doc, overlay = merge_effective_document(meta["document"], service, env)
        meta = {**meta, "document": doc, "overlay": {
            "updated_at": overlay.get("updated_at"),
            "operation_count": len(overlay.get("operations") or {}),
        }}
    if not include_document:
        meta = {**meta, "document": None}
    return meta


@router.post("/api/payloads/build")
async def api_payloads_build(body: PayloadBuildRequest) -> dict:
    """Schema-first payload build from live OpenAPI (+ overlay). No LLM."""
    return build_payload(
        service=body.service,
        environment=body.environment,
        method=body.method,
        path=body.path,
        operation_id=body.operation_id,
        api_id=body.api_id,
    )


@router.post("/api/payloads/ensure-working")
async def api_payloads_ensure_working(body: PayloadEnsureRequest) -> dict:
    """Build → Try proxy → on 2xx write set+overlay; optional one LLM fallback."""
    return await ensure_working_payload(
        service=body.service,
        environment=body.environment,
        method=body.method,
        path=body.path,
        operation_id=body.operation_id,
        api_id=body.api_id,
        write_back=body.write_back,
        allow_llm=body.allow_llm,
    )


@router.get("/api/catalog/{service}/openapi/overlay")
async def api_service_openapi_overlay(
    service: str,
    environment: str | None = Query(default=None),
) -> dict:
    env = environment or settings.default_environment
    return load_overlay(service, env)

@router.get("/api/catalog/{service}/openapi/versions")
async def api_service_openapi_versions(service: str) -> dict:
    """OpenAPI info.version (and reachability) per configured environment."""
    versions = openapi_versions_by_env(service)
    return {"service": service, "environments": versions, "count": len(versions)}


@router.get("/api/platform/health")
async def api_platform_health() -> dict:
    return await load_ops.platform_health()


@router.get("/api/platform/try-token")
async def api_platform_try_token() -> dict:
    """Bearer token for Swagger UI Try it out (platform identity; SPT-owned auth)."""
    token = platform_bearer_token()
    if not token:
        raise HTTPException(status_code=503, detail="SPT identity login unavailable")
    return {
        "token_type": "Bearer",
        "access_token": token,
        "identity_url": settings.spt_identity_url,
    }


@router.api_route(
    "/api/catalog/{service}/try/{environment}",
    methods=_TRY_METHODS,
)
@router.api_route(
    "/api/catalog/{service}/try/{environment}/{path:path}",
    methods=_TRY_METHODS,
)
async def api_service_try_proxy(
    service: str,
    environment: str,
    request: Request,
    path: str = "",
) -> Response:
    """Browser-safe Try it out proxy (same-origin → SPT → service). Avoids CORS / cluster DNS."""
    result = await proxy_try_request(
        service,
        environment,
        request.method,
        path,
        query=str(request.url.query or ""),
        headers={k: v for k, v in request.headers.items()},
        body=await request.body(),
    )
    return Response(
        content=result.get("body") or b"",
        status_code=int(result.get("status_code") or 502),
        headers=result.get("headers") or {"content-type": "application/json"},
    )


@router.get("/api/scripts")
async def api_scripts() -> dict:
    return scripts_bundle()


@router.get("/config")
async def config_preview() -> dict:
    from app.db.engine import store_mode

    return {
        "poc_target_url": settings.poc_target_url,
        "grafana_public_url": settings.grafana_public_url,
        "minio_console_url": settings.minio_public_console_url,
        "influxdb_bucket": settings.influxdb_bucket,
        "max_vus": settings.max_vus,
        "root_path": settings.root_path or "/",
        "ui_url": f"{settings.root_path.rstrip('/')}/ui" if settings.root_path else "/ui",
        "data_dir": settings.data_dir,
        "runner": "k6-local",
        "spt_store": store_mode(),
        "spt_acl_required": settings.spt_acl_required,
        "max_concurrent_runs": settings.spt_max_concurrent_runs,
        "mcp_path": "/mcp",
    }
