"""Generic OpenAPI → request payload builder (zero service coupling).

Uses only schema fields: example, default, enum, format, type, $ref.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def _slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", ".", value.strip().lower()).strip(".")
    return s or "op"


def api_id_for(method: str, path: str, operation_id: str | None = None) -> str:
    if operation_id:
        return _slug(operation_id)
    return _slug(f"{method}.{path}")


def operation_key(method: str, path: str, operation_id: str | None = None) -> str:
    if operation_id:
        return str(operation_id)
    return f"{method.lower()}:{path}"


def _resolve_ref(schema: dict[str, Any] | None, components: dict[str, Any], depth: int) -> dict[str, Any] | None:
    if not schema or depth > 6:
        return None
    ref = schema.get("$ref")
    if not ref:
        return schema
    name = str(ref).split("/")[-1]
    resolved = ((components or {}).get("schemas") or {}).get(name)
    return _resolve_ref(resolved, components, depth + 1) if isinstance(resolved, dict) else None


def example_from_schema(schema: dict[str, Any] | None, components: dict[str, Any] | None = None, depth: int = 0) -> Any:
    components = components or {}
    if not schema or not isinstance(schema, dict) or depth > 5:
        return None
    if schema.get("example") is not None:
        return schema["example"]
    if schema.get("default") is not None:
        return schema["default"]
    if schema.get("$ref"):
        resolved = _resolve_ref(schema, components, 0)
        return example_from_schema(resolved, components, depth + 1)
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    schema_type = schema.get("type")
    if schema_type == "object" or schema.get("properties"):
        out: dict[str, Any] = {}
        props = schema.get("properties") or {}
        for key in list(props.keys())[:16]:
            val = example_from_schema(props[key], components, depth + 1)
            if val is not None:
                out[key] = val
        return out
    if schema_type == "array":
        item = example_from_schema(schema.get("items") or {"type": "string"}, components, depth + 1)
        return [item] if item is not None else []
    if schema_type in ("integer", "number"):
        return 1
    if schema_type == "boolean":
        return True
    if schema_type == "string":
        fmt = str(schema.get("format") or "")
        if fmt == "date":
            return "2026-01-01"
        if fmt == "date-time":
            return "2026-01-01T00:00:00Z"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000001"
        return "example"
    return None


def example_from_param(param: dict[str, Any], components: dict[str, Any] | None = None) -> Any:
    if param.get("example") is not None:
        return param["example"]
    schema = param.get("schema") if isinstance(param.get("schema"), dict) else {}
    if schema.get("example") is not None:
        return schema["example"]
    if schema.get("default") is not None:
        return schema["default"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    # Generic pagination only (not service-specific catalogs)
    name = str(param.get("name") or "").lower()
    if name in ("page", "offset"):
        return 0
    if name in ("size", "limit"):
        return 10
    return example_from_schema(schema, components or {}, 0)


def find_operation(
    doc: dict[str, Any],
    *,
    method: str | None = None,
    path: str | None = None,
    operation_id: str | None = None,
    api_id: str | None = None,
) -> dict[str, Any] | None:
    paths = doc.get("paths") if isinstance(doc.get("paths"), dict) else {}
    m = (method or "").lower()
    want_api = _slug(api_id) if api_id else None
    for p, item in paths.items():
        if not isinstance(item, dict):
            continue
        for http_m in _HTTP_METHODS:
            op = item.get(http_m)
            if not isinstance(op, dict):
                continue
            oid = str(op.get("operationId") or "") or None
            cand_id = api_id_for(http_m, p, oid)
            if operation_id and oid == operation_id:
                return {"method": http_m, "path": p, "operation": op, "operation_id": oid, "api_id": cand_id}
            if want_api and cand_id == want_api:
                return {"method": http_m, "path": p, "operation": op, "operation_id": oid, "api_id": cand_id}
            if path and m and p == path and http_m == m:
                return {"method": http_m, "path": p, "operation": op, "operation_id": oid, "api_id": cand_id}
    return None


def build_request_from_operation(
    doc: dict[str, Any],
    *,
    method: str | None = None,
    path: str | None = None,
    operation_id: str | None = None,
    api_id: str | None = None,
    overlay_entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build path/query/body for one operation. Source: set|example|schema."""
    hit = find_operation(
        doc,
        method=method,
        path=path,
        operation_id=operation_id,
        api_id=api_id,
    )
    if not hit:
        return {
            "ok": False,
            "error": "operation_not_found",
            "source": None,
            "request": None,
        }

    op = hit["operation"]
    components = doc.get("components") if isinstance(doc.get("components"), dict) else {}
    overlay_entry = overlay_entry if isinstance(overlay_entry, dict) else {}

    path_params: dict[str, Any] = {}
    query: dict[str, Any] = {}
    source = "schema"

    # Prefer overlay (verified set) first
    ov_path = overlay_entry.get("path_params") if isinstance(overlay_entry.get("path_params"), dict) else {}
    ov_query = overlay_entry.get("query") if isinstance(overlay_entry.get("query"), dict) else {}
    if ov_path or ov_query or overlay_entry.get("body") is not None:
        source = str(overlay_entry.get("source") or "set")
        path_params.update(ov_path)
        query.update(ov_query)

    for param in op.get("parameters") or []:
        if not isinstance(param, dict) or not param.get("name"):
            continue
        name = str(param["name"])
        where = param.get("in")
        if where == "path" and name in path_params:
            continue
        if where == "query" and name in query:
            continue
        ex = example_from_param(param, components)
        if ex is None:
            continue
        if param.get("example") is not None or (param.get("schema") or {}).get("example") is not None:
            if source == "schema":
                source = "example"
        if where == "path":
            path_params[name] = ex
        elif where == "query":
            query[name] = ex

    body = overlay_entry.get("body") if "body" in overlay_entry else None
    if body is None:
        rb = op.get("requestBody")
        if isinstance(rb, dict):
            content = rb.get("content") if isinstance(rb.get("content"), dict) else {}
            media = None
            for ct, m in content.items():
                if "json" in str(ct).lower() and isinstance(m, dict):
                    media = m
                    break
            if media is None and content:
                first = next(iter(content.values()))
                media = first if isinstance(first, dict) else None
            if media:
                if media.get("example") is not None:
                    body = media["example"]
                    if source == "schema":
                        source = "example"
                elif isinstance(media.get("examples"), dict) and media["examples"]:
                    first_ex = next(iter(media["examples"].values()))
                    if isinstance(first_ex, dict) and first_ex.get("value") is not None:
                        body = first_ex["value"]
                        if source == "schema":
                            source = "example"
                else:
                    body = example_from_schema(media.get("schema"), components, 0)

    resolved_path = str(hit["path"])
    for k, v in path_params.items():
        resolved_path = resolved_path.replace("{" + k + "}", str(v))

    request = {
        "method": str(hit["method"]).upper(),
        "path": hit["path"],
        "resolved_path": resolved_path,
        "path_params": path_params,
        "query": query,
        "body": body,
        "operation_id": hit.get("operation_id"),
        "api_id": hit["api_id"],
    }
    return {
        "ok": True,
        "source": source,
        "operation_key": operation_key(hit["method"], hit["path"], hit.get("operation_id")),
        "request": request,
    }


def build_query_string(query: dict[str, Any] | None) -> str:
    if not query:
        return ""
    flat = {k: ("" if v is None else str(v)) for k, v in query.items()}
    return urlencode(flat)
