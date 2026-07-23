"""Build + Try ensure-working loop with optional LLM fallback."""
from __future__ import annotations

import json
from typing import Any

from app.catalog_loader import load_openapi_document, proxy_try_request
from app.config import settings
from app.fin_api_client import llm_suggest_payload
from app.openapi_overlay import load_overlay, upsert_operation_overlay
from app.payload_builder import build_query_string, build_request_from_operation, find_operation
from app.payload_store import save_payload, upsert_api_in_payload_set


def _effective_doc(service: str, environment: str) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    meta = load_openapi_document(service, environment)
    doc = meta.get("document") if isinstance(meta.get("document"), dict) else None
    overlay = load_overlay(service, environment or settings.default_environment)
    return doc, meta, overlay


def build_payload(
    *,
    service: str,
    environment: str | None = None,
    method: str | None = None,
    path: str | None = None,
    operation_id: str | None = None,
    api_id: str | None = None,
) -> dict[str, Any]:
    env = environment or settings.default_environment
    doc, meta, overlay = _effective_doc(service, env)
    if not doc:
        return {
            "ok": False,
            "error": meta.get("error") or "openapi_unavailable",
            "service": service,
            "environment": env,
        }
    hit = find_operation(doc, method=method, path=path, operation_id=operation_id, api_id=api_id)
    op_key = None
    overlay_entry = None
    if hit:
        from app.payload_builder import operation_key

        op_key = operation_key(hit["method"], hit["path"], hit.get("operation_id"))
        overlay_entry = (overlay.get("operations") or {}).get(op_key)
        if overlay_entry is None and hit.get("operation_id"):
            overlay_entry = (overlay.get("operations") or {}).get(hit["operation_id"])

    built = build_request_from_operation(
        doc,
        method=method,
        path=path,
        operation_id=operation_id,
        api_id=api_id,
        overlay_entry=overlay_entry,
    )
    return {
        **built,
        "service": service,
        "environment": env,
        "openapi_version": meta.get("version"),
        "operation_key": built.get("operation_key") or op_key,
    }


async def ensure_working_payload(
    *,
    service: str,
    environment: str | None = None,
    method: str | None = None,
    path: str | None = None,
    operation_id: str | None = None,
    api_id: str | None = None,
    write_back: bool = True,
    allow_llm: bool | None = None,
) -> dict[str, Any]:
    env = environment or settings.default_environment
    built = build_payload(
        service=service,
        environment=env,
        method=method,
        path=path,
        operation_id=operation_id,
        api_id=api_id,
    )
    if not built.get("ok") or not isinstance(built.get("request"), dict):
        return built

    request = dict(built["request"])
    source = built.get("source") or "schema"
    try_result = await _try_once(service, env, request)
    status = int(try_result.get("status_code") or 0)
    ok_http = 200 <= status < 300

    llm_used = False
    if not ok_http and (allow_llm if allow_llm is not None else settings.spt_payload_llm_fallback):
        llm = await llm_suggest_payload(
            service=service,
            method=str(request.get("method") or "GET"),
            path=str(request.get("path") or ""),
            openapi_snippet={"operation_id": request.get("operation_id"), "path": request.get("path")},
            error_hint=f"status={status}",
        )
        llm_used = True
        if llm.get("ok") and isinstance(llm.get("request"), dict):
            suggested = llm["request"]
            request = {
                **request,
                "path_params": suggested.get("path_params") or suggested.get("pathParams") or request.get("path_params"),
                "query": suggested.get("query") or request.get("query"),
                "body": suggested.get("body") if "body" in suggested else request.get("body"),
                "resolved_path": suggested.get("resolved_path") or request.get("resolved_path"),
            }
            # re-resolve path if params changed
            if request.get("path") and request.get("path_params"):
                resolved = str(request["path"])
                for k, v in (request.get("path_params") or {}).items():
                    resolved = resolved.replace("{" + k + "}", str(v))
                request["resolved_path"] = resolved
            source = "llm-fallback"
            try_result = await _try_once(service, env, request)
            status = int(try_result.get("status_code") or 0)
            ok_http = 200 <= status < 300

    result: dict[str, Any] = {
        "ok": ok_http,
        "service": service,
        "environment": env,
        "source": source,
        "llm_attempted": llm_used,
        "request": request,
        "try": {
            "status_code": status,
            "upstream_url": try_result.get("upstream_url"),
            "error": try_result.get("error"),
        },
        "operation_key": built.get("operation_key"),
        "api_id": request.get("api_id"),
    }

    if ok_http and write_back:
        op_key = str(built.get("operation_key") or request.get("operation_id") or request.get("api_id"))
        upsert_operation_overlay(
            service,
            env,
            operation_key=op_key,
            path_params=request.get("path_params") or {},
            query=request.get("query") or {},
            body=request.get("body"),
            source=source if source != "schema" else "ensure-working",
        )
        api_id_val = str(request.get("api_id") or "unknown")
        saved = save_payload(
            {
                "service": service,
                "api_id": api_id_val,
                "name": "working",
                "request": {
                    "method": request.get("method"),
                    "path": request.get("path"),
                    "query": request.get("query") or {},
                    "path_params": request.get("path_params") or {},
                    "body": request.get("body"),
                },
                "response": {
                    "status": status,
                },
                "meta": {"source": source, "ensure_working": True},
            },
            bump=True,
        )
        payload_set = upsert_api_in_payload_set(
            service,
            api_id_val,
            request=saved.get("request"),
            response=saved.get("response"),
            meta={"source": source},
            name="working",
            bump_set=False,
        )
        result["payload"] = saved
        result["payload_set"] = {
            "version": payload_set.get("version"),
            "active": True,
        }
        result["overlay_written"] = True

    return result


async def _try_once(service: str, environment: str, request: dict[str, Any]) -> dict[str, Any]:
    path = str(request.get("resolved_path") or request.get("path") or "").lstrip("/")
    query = request.get("query") if isinstance(request.get("query"), dict) else {}
    qs = build_query_string(query) if query else ""
    body_raw: bytes | None = None
    headers = {"Accept": "application/json"}
    if request.get("body") is not None and str(request.get("method") or "GET").upper() not in ("GET", "HEAD"):
        body_raw = json.dumps(request["body"]).encode("utf-8")
        headers["Content-Type"] = "application/json"
    return await proxy_try_request(
        service,
        environment,
        str(request.get("method") or "GET"),
        path,
        query=qs,
        headers=headers,
        body=body_raw,
    )
