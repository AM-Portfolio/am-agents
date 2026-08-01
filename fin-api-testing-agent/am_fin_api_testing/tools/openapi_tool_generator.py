"""
openapi_tool_generator.py
=========================
Parses OpenAPI specs (using the `openapi-pydantic` framework) and produces:
  1. OpenAI-compatible tool schemas   → fed into TOOL_REGISTRY
  2. An async HTTP executor (httpx)   → called by execute_tool()

No custom parser classes – uses openapi-pydantic for spec parsing
and httpx (already in requirements) for execution.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ─── Schema Helpers ──────────────────────────────────────────────────────────


def _resolve_ref(ref: str, spec: Dict) -> Dict:
    """Follow a $ref like '#/components/schemas/Foo' and return the target dict."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for p in parts:
        node = node.get(p, {})
    return node


def _schema_to_properties(schema: Dict, spec: Dict) -> tuple[Dict, List[str]]:
    """
    Recursively expand a JSON Schema object into (properties_dict, required_list).
    Handles $ref, allOf, oneOf, anyOf.
    """
    if not schema:
        return {}, []

    # Resolve top-level $ref
    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"], spec)

    # Merge allOf / oneOf / anyOf schemas
    merged: Dict = {}
    required: List[str] = list(schema.get("required", []))
    for combiner in ("allOf", "oneOf", "anyOf"):
        for sub in schema.get(combiner, []):
            resolved = sub if "$ref" not in sub else _resolve_ref(sub["$ref"], spec)
            props, reqs = _schema_to_properties(resolved, spec)
            merged.update(props)
            required.extend(reqs)

    # Direct properties
    for name, prop_schema in schema.get("properties", {}).items():
        if "$ref" in prop_schema:
            prop_schema = _resolve_ref(prop_schema["$ref"], spec)
        merged[name] = {
            "type": prop_schema.get("type", "string"),
            "description": prop_schema.get("description", name),
        }
        if "enum" in prop_schema:
            merged[name]["enum"] = prop_schema["enum"]

    return merged, list(set(required))


# ─── Core Converter ──────────────────────────────────────────────────────────


def spec_to_tools(spec_dict: Dict[str, Any], base_url: str = "") -> List[Dict]:
    """
    Convert a raw OpenAPI spec dict to a list of tool schemas.

    Each returned dict has the OpenAI function-calling shape PLUS a private
    '_meta' key used by execute_openapi_tool() for routing – '_meta' is
    stripped before the schema is sent to the LLM.

    Args:
        spec_dict: The parsed OpenAPI JSON/YAML dict.
        base_url:  Override the base URL (e.g. 'http://localhost:8092').
                   Falls back to spec servers[0].url if empty.

    Returns:
        List of tool schema dicts.
    """
    tools: List[Dict] = []

    # Determine base URL
    if not base_url:
        servers = spec_dict.get("servers", [])
        base_url = servers[0].get("url", "") if servers else ""

    paths = spec_dict.get("paths", {})
    for path, path_item in paths.items():
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if not operation:
                continue

            # Skip destructive ops by default
            if method in ("delete",):
                continue

            op_id = operation.get("operationId") or _derive_op_id(method, path)
            summary = operation.get("summary") or operation.get("description") or op_id

            # Build parameters schema
            properties: Dict = {}
            required: List[str] = []

            # Path / query parameters
            for param in operation.get("parameters", []):
                if "$ref" in param:
                    param = _resolve_ref(param["$ref"], spec_dict)
                p_name = param.get("name", "")
                p_schema = param.get("schema", {})
                if "$ref" in p_schema:
                    p_schema = _resolve_ref(p_schema["$ref"], spec_dict)
                properties[p_name] = {
                    "type": p_schema.get("type", "string"),
                    "description": param.get("description", p_name),
                }
                if param.get("required"):
                    required.append(p_name)

            # Request body
            body = operation.get("requestBody", {})
            if body:
                content = body.get("content", {})
                json_content = content.get("application/json", {})
                body_schema = json_content.get("schema", {})
                if "$ref" in body_schema:
                    body_schema = _resolve_ref(body_schema["$ref"], spec_dict)
                props, reqs = _schema_to_properties(body_schema, spec_dict)
                properties.update(props)
                required.extend(reqs)

            tool = {
                "type": "function",
                "function": {
                    "name": op_id,
                    "description": summary,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": list(set(required)),
                    },
                },
                # Private routing metadata – NOT sent to LLM
                "_meta": {
                    "method": method,
                    "path": path,
                    "base_url": base_url.rstrip("/"),
                    "op_id": op_id,
                },
            }
            tools.append(tool)
            logger.debug("Generated tool: %s  %s %s", op_id, method.upper(), path)

    logger.info("spec_to_tools: generated %d tools from spec (base_url=%s)", len(tools), base_url)
    return tools


def _derive_op_id(method: str, path: str) -> str:
    """Derive a safe operationId from method + path when none is provided."""
    safe = re.sub(r"[^a-zA-Z0-9]", "_", path).strip("_")
    return f"{method}_{safe}"


# ─── HTTP Executor ────────────────────────────────────────────────────────────


async def execute_openapi_tool(meta: Dict[str, Any], args: Dict[str, Any]) -> str:
    """
    Execute the real HTTP call for an auto-generated OpenAPI tool.

    Uses httpx (already in requirements) – no custom HTTP client class.

    Args:
        meta: The '_meta' dict from the tool schema
              (keys: method, path, base_url, op_id).
        args: The arguments supplied by the LLM or MCP client.

    Returns:
        JSON string with keys 'status' and 'body'.
    """
    method = meta["method"].upper()
    path = meta["path"]
    base_url = meta["base_url"]

    # Fill path parameters  e.g. /users/{id} → /users/42
    path_param_names = set(re.findall(r"\{(\w+)\}", path))
    for key in path_param_names:
        if key in args:
            path = path.replace(f"{{{key}}}", str(args[key]))

    url = base_url + path
    remaining = {k: v for k, v in args.items() if k not in path_param_names}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method in ("GET", "DELETE"):
                resp = await client.request(method, url, params=remaining or None)
            else:
                resp = await client.request(method, url, json=remaining or None)

        content_type = resp.headers.get("content-type", "")
        body = resp.json() if "application/json" in content_type else resp.text

        return json.dumps({"status": resp.status_code, "body": body}, default=str)

    except httpx.TimeoutException:
        return json.dumps({"error": f"Request to {url} timed out", "status": 504})
    except Exception as exc:
        logger.error("execute_openapi_tool failed for %s %s: %s", method, url, exc)
        return json.dumps({"error": str(exc), "status": 500})
