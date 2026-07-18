"""Load verify check catalog (catalog/verify/checks.yaml)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


_DEFAULT_CHECKS: list[dict[str, Any]] = [
    {
        "check_ref": "verify.k8s.endpoints.ready",
        "kind": "metrics",
        "query_ref": "k8s.endpoints.ready",
        "pass_when": "value > 0",
    },
    {
        "check_ref": "verify.service.alive",
        "kind": "metrics",
        "query_ref": "redis.service.alive",
        "pass_when": "value == 1",
    },
]


def _catalog_path() -> Path:
    env = os.getenv("VERIFY_CATALOG_PATH", "").strip()
    if env:
        return Path(env)
    # platform_worker/.../activities -> am-agents/
    here = Path(__file__).resolve()
    return here.parents[3] / "catalog" / "verify" / "checks.yaml"


def load_verify_checks() -> list[dict[str, Any]]:
    path = _catalog_path()
    if not path.is_file():
        return list(_DEFAULT_CHECKS)
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        checks = data.get("checks") or []
        return list(checks) if checks else list(_DEFAULT_CHECKS)
    except ImportError:
        # Minimal fallback: return defaults (catalog still authoritative when PyYAML present)
        return list(_DEFAULT_CHECKS)
