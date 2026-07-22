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
)
from app.config import settings

router = APIRouter(tags=["platform"])

_TRY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@router.get("/ready")
async def ready() -> dict:
    h = await load_ops.platform_health()
    return {"status": "ready", "platform": h}


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
    return {
        "service": service,
        "environment": env,
        "target_url": default_target_for_service(service, env),
        "runtime": (reg or {}).get("runtime") or data.get("runtime"),
        "openapi_version": data.get("openapi_version"),
        **data,
        "count": len(data.get("apis") or []),
    }


@router.get("/api/catalog/{service}/openapi/document")
async def api_service_openapi_document(
    service: str,
    environment: str | None = Query(default=None),
):
    """Raw OpenAPI JSON proxied by SPT (browser-reachable; cluster DNS is not)."""
    meta = load_openapi_document(service, environment)
    if not meta.get("ok") or not isinstance(meta.get("document"), dict):
        raise HTTPException(
            status_code=502,
            detail=meta.get("error") or f"OpenAPI unavailable for {service}",
        )
    return JSONResponse(
        content=meta["document"],
        headers={
            "X-SPT-OpenAPI-Source": str(meta.get("openapi_url") or ""),
            "X-SPT-Service": service,
            "X-SPT-Environment": str(meta.get("environment") or ""),
        },
    )


@router.get("/api/catalog/{service}/openapi")
async def api_service_openapi(
    service: str,
    environment: str | None = Query(default=None),
    include_document: bool = Query(default=True, description="Include full OpenAPI JSON"),
) -> dict:
    """Live OpenAPI document + registration config for Swagger-style Specs UI."""
    meta = load_openapi_document(service, environment)
    if not include_document:
        meta = {**meta, "document": None}
    return meta


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
    }
