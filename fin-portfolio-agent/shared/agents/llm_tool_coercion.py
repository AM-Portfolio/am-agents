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


def coerce_llm_tool_response(    response: Any,
    relevant_tools: List[Dict[str, Any]],
    *,
    default_args: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Return response unchanged when it already has tool_calls.

    Some LiteLLM models emit ``get_portfolio_summary()`` as plain text instead of
    structured tool_calls; convert that into a synthetic call the graph can execute.
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

    known = {
        t.get("function", {}).get("name")
        for t in relevant_tools
        if t.get("function", {}).get("name")
    }
    if not known:
        from shared.tools.registry import TOOL_REGISTRY

        known = {
            t.get("function", {}).get("name")
            for t in TOOL_REGISTRY
            if t.get("function", {}).get("name")
        }

    match = _TEXT_TOOL_RE.match(text)
    if not match:
        return response

    name = match.group(1)
    if name not in known:
        return response

    raw_args = match.group(2).strip()
    args: Dict[str, Any] = {}
    if raw_args:
        if raw_args.startswith("{"):
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    args = parsed
            except json.JSONDecodeError:
                return response
        else:
            return response

    if default_args:
        for key, value in default_args.items():
            args.setdefault(key, value)

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
