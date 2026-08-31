"""Coerce plain-text LLM tool hints into OpenAI-style tool_calls."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Optional

_TEXT_TOOL_RE = re.compile(
    r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)\s*$",
    re.DOTALL,
)
_TOOL_CALL_BLOCK_RE = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)
_XML_FUNCTION_EQ_RE = re.compile(
    r"<function=([a-zA-Z_][a-zA-Z0-9_]*)>",
    re.IGNORECASE,
)
_XML_FUNCTION_TAG_RE = re.compile(
    r"<function>\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*</function>",
    re.IGNORECASE,
)
_XML_PARAMETER_EQ_RE = re.compile(
    r"<parameter=([a-zA-Z_][a-zA-Z0-9_]*)>\s*(.*?)\s*</parameter>",
    re.DOTALL | re.IGNORECASE,
)
_XML_PARAMETER_ATTR_RE = re.compile(
    r'<parameter\s+name=["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']\s*>(.*?)</parameter>',
    re.DOTALL | re.IGNORECASE,
)
_MARKDOWN_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)
_JSON_TOOL_KEY_RE = re.compile(
    r'\{\s*"(?:tool|name|function)"\s*:\s*"([a-zA-Z_][a-zA-Z0-9_]*)"',
    re.IGNORECASE,
)


def describe_coercion(before: Any, after: Any) -> Optional[Dict[str, Any]]:
    """Return metadata when plain-text was coerced into tool_calls."""
    if not (isinstance(after, dict) and after.get("tool_calls")):
        return None
    if isinstance(before, dict) and before.get("tool_calls"):
        return None
    raw = before if isinstance(before, str) else (before.get("content") if isinstance(before, dict) else str(before))
    return {
        "raw_text": str(raw).strip(),
        "tool_calls": after.get("tool_calls"),
        "coerced": True,
    }


def _known_tool_names(relevant_tools: List[Dict[str, Any]]) -> set[str]:
    from shared.tools.registry import TOOL_REGISTRY

    known = {
        t.get("function", {}).get("name")
        for t in list(relevant_tools) + list(TOOL_REGISTRY)
        if t.get("function", {}).get("name")
    }
    return {n for n in known if n}


def _build_tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "content": "",
        "tool_calls": [
            {
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args),
                },
            }
        ],
    }


def _extract_tool_from_dict(data: Any) -> tuple[str, Dict[str, Any]] | None:
    if not isinstance(data, dict):
        return None
    name = data.get("name") or data.get("function") or data.get("tool")
    if not isinstance(name, str) or not name.strip():
        return None
    raw_args = data.get("arguments") or data.get("parameters") or data.get("args") or {}
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except json.JSONDecodeError:
            raw_args = {}
    if not isinstance(raw_args, dict):
        raw_args = {}
    return name.strip(), raw_args


def _parse_xml_parameters(body: str) -> Dict[str, Any]:
    """Extract ``<parameter=name>value</parameter>`` pairs from XML tool blocks."""
    params: Dict[str, Any] = {}
    for pattern in (_XML_PARAMETER_EQ_RE, _XML_PARAMETER_ATTR_RE):
        for match in pattern.finditer(body):
            key = match.group(1).strip()
            value = match.group(2).strip()
            if key:
                params[key] = value
    return params


def _parse_xml_tool_block(block: str) -> tuple[str, Dict[str, Any]] | None:
    """Parse ``<tool_call>…</tool_call>`` bodies (JSON or XML function tags)."""
    body = block.strip()
    if not body:
        return None

    if body.startswith("{"):
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None
        return _extract_tool_from_dict(data)

    xml_args = _parse_xml_parameters(body)

    for pattern in (_XML_FUNCTION_EQ_RE, _XML_FUNCTION_TAG_RE):
        match = pattern.search(body)
        if match:
            return match.group(1), xml_args

    return None


def _coerce_from_text(text: str, known: set[str], default_args: Optional[Dict[str, Any]]) -> Any | None:
    """Return synthetic tool_calls dict when *text* encodes a known tool invocation."""
    block_match = _TOOL_CALL_BLOCK_RE.search(text)
    if block_match:
        parsed = _parse_xml_tool_block(block_match.group(1))
        if parsed:
            name, args = parsed
            if name in known:
                merged = dict(default_args or {})
                merged.update(args)
                return _build_tool_call(name, merged)

    for fence in _MARKDOWN_JSON_FENCE_RE.finditer(text):
        try:
            data = json.loads(fence.group(1))
        except json.JSONDecodeError:
            continue
        parsed = _extract_tool_from_dict(data)
        if parsed and parsed[0] in known:
            name, args = parsed
            merged = dict(default_args or {})
            merged.update(args)
            return _build_tool_call(name, merged)

    for key_match in _JSON_TOOL_KEY_RE.finditer(text):
        try:
            data, _ = json.JSONDecoder().raw_decode(text[key_match.start():])
        except json.JSONDecodeError:
            continue
        parsed = _extract_tool_from_dict(data)
        if parsed and parsed[0] in known:
            name, args = parsed
            merged = dict(default_args or {})
            merged.update(args)
            return _build_tool_call(name, merged)

    match = _TEXT_TOOL_RE.match(text.strip())
    if not match:
        return None

    name = match.group(1)
    if name not in known:
        return None

    raw_args = match.group(2).strip()
    args: Dict[str, Any] = {}
    if raw_args:
        if not raw_args.startswith("{"):
            return None
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        args = parsed

    if default_args:
        for key, value in default_args.items():
            args.setdefault(key, value)

    return _build_tool_call(name, args)


def coerce_llm_tool_response(
    response: Any,
    relevant_tools: List[Dict[str, Any]],
    *,
    default_args: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Return response unchanged when it already has tool_calls.

    Some LiteLLM models emit plain text instead of structured tool_calls, e.g.
    ``get_portfolio_summary()`` or ``<tool_call><function=name></function></tool_call>``.
    Convert those into synthetic calls the graph can execute.
    """
    if isinstance(response, dict) and response.get("tool_calls"):
        return response

    text = ""
    if isinstance(response, str):
        text = response.strip()
    elif isinstance(response, dict):
        text = (response.get("content") or "").strip()

    if not text:
        return response

    known = _known_tool_names(relevant_tools)
    coerced = _coerce_from_text(text, known, default_args)
    return coerced if coerced is not None else response
