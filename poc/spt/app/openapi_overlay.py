"""SPT-local OpenAPI overlays — examples that survive across fetches.

Stored under ``{data_dir}/openapi_overlays/{service}/{env}.json``.
Never imports service Java; only patches live OpenAPI JSON.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def overlay_root() -> Path:
    path = Path(settings.data_dir) / "openapi_overlays"
    path.mkdir(parents=True, exist_ok=True)
    return path


def overlay_path(service: str, environment: str) -> Path:
    env = (environment or "dev").strip().lower() or "dev"
    d = overlay_root() / service
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{env}.json"


def load_overlay(service: str, environment: str) -> dict[str, Any]:
    path = overlay_path(service, environment)
    if not path.is_file():
        return {
            "service": service,
            "environment": (environment or "dev").lower(),
            "operations": {},
            "updated_at": None,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("overlay not object")
        data.setdefault("service", service)
        data.setdefault("environment", (environment or "dev").lower())
        data.setdefault("operations", {})
        return data
    except (json.JSONDecodeError, ValueError):
        return {
            "service": service,
            "environment": (environment or "dev").lower(),
            "operations": {},
            "updated_at": None,
        }


def save_overlay(service: str, environment: str, overlay: dict[str, Any]) -> dict[str, Any]:
    env = (environment or "dev").strip().lower() or "dev"
    record = {
        "service": service,
        "environment": env,
        "operations": overlay.get("operations") if isinstance(overlay.get("operations"), dict) else {},
        "updated_at": _now(),
    }
    path = overlay_path(service, env)
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return record


def upsert_operation_overlay(
    service: str,
    environment: str,
    *,
    operation_key: str,
    path_params: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    body: Any = None,
    source: str = "set",
) -> dict[str, Any]:
    overlay = load_overlay(service, environment)
    ops = dict(overlay.get("operations") or {})
    prev = dict(ops.get(operation_key) or {})
    entry = {
        **prev,
        "path_params": path_params if path_params is not None else prev.get("path_params") or {},
        "query": query if query is not None else prev.get("query") or {},
        "body": body if body is not None else prev.get("body"),
        "source": source,
        "updated_at": _now(),
    }
    ops[operation_key] = entry
    overlay["operations"] = ops
    return save_overlay(service, environment, overlay)


def _find_operation(
    doc: dict[str, Any],
    *,
    method: str | None = None,
    path: str | None = None,
    operation_id: str | None = None,
) -> tuple[str, str, dict[str, Any]] | None:
    paths = doc.get("paths") if isinstance(doc.get("paths"), dict) else {}
    m = (method or "").lower()
    for p, item in paths.items():
        if not isinstance(item, dict):
            continue
        for http_m in _HTTP_METHODS:
            op = item.get(http_m)
            if not isinstance(op, dict):
                continue
            oid = str(op.get("operationId") or "")
            if operation_id and oid == operation_id:
                return p, http_m, op
            if path and m and p == path and http_m == m:
                return p, http_m, op
    return None


def apply_overlay_to_document(doc: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied OpenAPI doc with overlay examples injected."""
    out = deepcopy(doc) if isinstance(doc, dict) else {}
    ops = overlay.get("operations") if isinstance(overlay.get("operations"), dict) else {}
    if not ops:
        return out

    for key, entry in ops.items():
        if not isinstance(entry, dict):
            continue
        hit = _find_operation(out, operation_id=key)
        if hit is None and ":" in key:
            # method:path fallback key
            method, _, path = key.partition(":")
            hit = _find_operation(out, method=method, path=path)
        if hit is None:
            continue
        _path, _method, op = hit
        path_params = entry.get("path_params") if isinstance(entry.get("path_params"), dict) else {}
        query = entry.get("query") if isinstance(entry.get("query"), dict) else {}
        for param in op.get("parameters") or []:
            if not isinstance(param, dict):
                continue
            name = str(param.get("name") or "")
            if param.get("in") == "path" and name in path_params:
                param["example"] = path_params[name]
            if param.get("in") == "query" and name in query:
                param["example"] = query[name]
        body = entry.get("body")
        if body is not None:
            rb = op.get("requestBody")
            if isinstance(rb, dict):
                content = rb.get("content") if isinstance(rb.get("content"), dict) else {}
                for media in content.values():
                    if isinstance(media, dict):
                        media["example"] = body
    return out


def merge_effective_document(
    live_doc: dict[str, Any],
    service: str,
    environment: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    overlay = load_overlay(service, environment)
    return apply_overlay_to_document(live_doc, overlay), overlay
