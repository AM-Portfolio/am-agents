from __future__ import annotations

from typing import Any


def sanitize_payload(value: Any, *, max_chars: int = 8000) -> Any:
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + "…"
    if isinstance(value, dict):
        return {k: sanitize_payload(v, max_chars=max_chars) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(v, max_chars=max_chars) for v in value[:50]]
    return value


def tool_fqn(backend: str, operation: str) -> str:
    return f"{backend}.{operation}"


def trace_name(backend: str | None = None, operation: str | None = None, *, pending: bool = False) -> str:
    if backend and operation:
        return f"tool-agent · {backend}.{operation}"
    if backend:
        return f"tool-agent · {backend}"
    return "tool-agent · pending intent" if pending else "tool-agent query"


def trace_tags(
    backend: str | None = None,
    operation: str | None = None,
    *,
    parse_source: str | None = None,
    agent_caller: str | None = None,
) -> list[str]:
    tags = ["tool-agent"]
    if backend:
        tags.append(f"backend:{backend}")
    if operation:
        tags.append(f"operation:{operation}")
    if parse_source:
        tags.append(f"parse:{parse_source}")
    if agent_caller:
        tags.append(f"caller:{agent_caller}")
    return tags


def trace_metadata(
    *,
    backend: str | None = None,
    backend_hint: str | None = None,
    operation: str | None = None,
    agent_caller: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"source": "tool-agent"}
    if backend:
        meta["backend"] = backend
    if backend_hint:
        meta["backend_hint"] = backend_hint
    if operation:
        meta["operation"] = operation
    if agent_caller:
        meta["agent_caller"] = agent_caller
    if extra:
        meta.update(extra)
    return meta
