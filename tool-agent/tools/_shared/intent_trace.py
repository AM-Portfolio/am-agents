from __future__ import annotations

import contextvars
from typing import Any, Literal

_resolve_trace: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "resolve_trace", default={}
)


def set_resolve_trace(**fields: Any) -> None:
    current = dict(_resolve_trace.get())
    current.update(trace_fields(**fields))
    _resolve_trace.set(current)


def get_resolve_trace() -> dict[str, Any]:
    return dict(_resolve_trace.get())


def clear_resolve_trace() -> None:
    _resolve_trace.set({})


ResolveMethod = Literal[
    "convention",
    "entity",
    "cache_fuzzy",
    "catalog_static",
    "passthrough",
    "unknown",
]

CatalogSource = Literal["live", "stale", "offline"]


def trace_fields(
    *,
    resolve_method: ResolveMethod | None = None,
    matched_key: str | None = None,
    catalog_source: CatalogSource | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if resolve_method:
        out["resolve_method"] = resolve_method
    if matched_key:
        out["matched_key"] = matched_key
    if catalog_source:
        out["catalog_source"] = catalog_source
    return out


def merge_trace_metadata(base: dict[str, Any] | None, **fields: Any) -> dict[str, Any]:
    merged = dict(base or {})
    merged.update({k: v for k, v in fields.items() if v is not None})
    return merged
