"""Convert live OpenAPI documents into SPT catalog API entries."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
import yaml

logger = logging.getLogger(__name__)

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

# Runtime → default OpenAPI path on the live service
OPENAPI_PATH_BY_RUNTIME: dict[str, str] = {
    "java": "/v3/api-docs",
    "python": "/openapi.json",
    "fastapi": "/openapi.json",
    "spring": "/v3/api-docs",
}


def default_openapi_path(runtime: str | None) -> str:
    key = (runtime or "java").strip().lower()
    return OPENAPI_PATH_BY_RUNTIME.get(key, "/v3/api-docs")


def _slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", ".", value.strip().lower()).strip(".")
    return s or "op"


def _param_example(param: dict[str, Any]) -> str | None:
    if param.get("example") is not None:
        return str(param["example"])
    schema = param.get("schema") or {}
    if schema.get("example") is not None:
        return str(schema["example"])
    if schema.get("default") is not None:
        return str(schema["default"])
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return str(enum[0])
    # Common Spring path hints
    name = str(param.get("name") or "").lower()
    if name in ("timeframe", "time_frame"):
        return "1D"
    if name in ("page", "size", "limit", "offset"):
        return "0" if name != "size" and name != "limit" else "10"
    return None


def _resolve_path(path: str, parameters: list[dict[str, Any]]) -> str | None:
    """Fill path templates; return None if a required path param has no example."""
    out = path
    for match in re.finditer(r"\{([^}/]+)\}", path):
        name = match.group(1)
        param = next(
            (p for p in parameters if p.get("in") == "path" and p.get("name") == name),
            {"name": name, "required": True},
        )
        example = _param_example(param)
        if example is None:
            return None
        out = out.replace("{" + name + "}", example)
    return out


def _needs_auth(doc: dict[str, Any], op: dict[str, Any], path: str = "") -> bool:
    # Explicit empty security array = public endpoint
    if op.get("security") is not None:
        return bool(op.get("security"))
    if doc.get("security"):
        return True
    for param in op.get("parameters") or []:
        if str(param.get("name") or "").lower() == "authorization":
            return True
    # Spring often puts bearer in components without per-op security
    schemes = ((doc.get("components") or {}).get("securitySchemes")) or {}
    if schemes:
        return True
    # Many platform services omit securitySchemes in /v3/api-docs but still require JWT.
    # Treat health/docs as public; everything else needs auth for load tests.
    pl = str(path or "").lower()
    public_hints = (
        "/actuator/health",
        "/actuator/info",
        "/health",
        "/api-docs",
        "/v3/api-docs",
        "/openapi",
        "/swagger",
    )
    if any(h in pl for h in public_hints):
        return False
    return True


def openapi_to_apis(
    doc: dict[str, Any],
    *,
    include_mutating: bool = False,
) -> list[dict[str, Any]]:
    """Map OpenAPI paths → SPT api rows. Prefer safe GETs; skip unresolved path params."""
    paths = doc.get("paths") or {}
    apis: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw_path, item in paths.items():
        if not isinstance(item, dict):
            continue
        shared_params = list(item.get("parameters") or [])
        for method in _HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            if not include_mutating and method not in ("get", "head"):
                continue
            params = shared_params + list(op.get("parameters") or [])
            resolved = _resolve_path(str(raw_path), params)
            if resolved is None:
                logger.debug("skip openapi op %s %s (missing path examples)", method, raw_path)
                continue

            op_id = str(op.get("operationId") or f"{method}.{raw_path}")
            api_id = _slug(op_id)
            if api_id in seen:
                api_id = _slug(f"{method}.{raw_path}")
            seen.add(api_id)

            query: dict[str, str] = {}
            for param in params:
                if param.get("in") != "query":
                    continue
                name = str(param.get("name") or "")
                if not name:
                    continue
                example = _param_example(param)
                if example is not None:
                    query[name] = example
                elif param.get("required"):
                    # required query without example — skip whole op
                    resolved = None
                    break
            if resolved is None:
                continue

            headers: dict[str, str] = {"Accept": "application/json"}
            if _needs_auth(doc, op, str(raw_path)):
                headers["Authorization"] = "{{env.SPT_AUTH_TOKEN}}"

            summary = str(op.get("summary") or op.get("operationId") or f"{method.upper()} {resolved}")
            apis.append(
                {
                    "id": api_id,
                    "name": summary,
                    "method": method.upper(),
                    "path": resolved,
                    "headers": headers,
                    "query": query,
                    "body": None,
                    "checks": ["status_2xx"],
                    "source": "openapi",
                }
            )

    # Always ensure a health probe if present in doc or as convention fallback handled by caller
    return apis


def parse_openapi_bytes(raw: bytes, content_type: str = "") -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    ct = (content_type or "").lower()
    if "yaml" in ct or text.lstrip().startswith(("openapi:", "swagger:")):
        data = yaml.safe_load(text)
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("OpenAPI document is not an object")
    return data


def fetch_openapi_sync(
    url: str,
    *,
    timeout: float = 20.0,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers=headers or {})
        resp.raise_for_status()
        return parse_openapi_bytes(resp.content, resp.headers.get("content-type", ""))


async def fetch_openapi(
    url: str,
    *,
    timeout: float = 20.0,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers or {})
        resp.raise_for_status()
        return parse_openapi_bytes(resp.content, resp.headers.get("content-type", ""))


def openapi_url(target_url: str, openapi_path: str) -> str:
    path = openapi_path if openapi_path.startswith("/") else f"/{openapi_path}"
    return f"{target_url.rstrip('/')}{path}"
