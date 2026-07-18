from __future__ import annotations

import os


def resolve_provider(*, env_var: str, default: str, allowed: set[str] | frozenset[str]) -> str:
    raw = (os.environ.get(env_var) or default).strip().lower()
    if raw not in allowed:
        raise ValueError(f"{env_var}={raw!r} not in {sorted(allowed)}")
    return raw
