"""Load test target definitions from wrapper JSON files."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.profiles.base import TargetConfig
from app.profiles.registry import profile_for_mode

_ENV_REF = re.compile(r"\$\{([^}]+)\}")


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    return values


def resolve_env_refs(value: str, env: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in env:
            raise KeyError(f"Missing env var for target ref: {key}")
        return env[key]

    return _ENV_REF.sub(repl, value)


def _resolve_obj(obj: Any, env: dict[str, str]) -> Any:
    if isinstance(obj, str):
        return resolve_env_refs(obj, env) if "${" in obj else obj
    if isinstance(obj, dict):
        return {k: _resolve_obj(v, env) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_obj(v, env) for v in obj]
    return obj


def load_targets_file(
    path: Path,
    *,
    env: dict[str, str] | None = None,
    env_file: Path | None = None,
) -> dict[str, Any]:
    merged_env = dict(os.environ)
    if env_file:
        merged_env.update(load_env_file(env_file))
    if env:
        merged_env.update(env)

    raw = json.loads(path.read_text(encoding="utf-8"))
    return _resolve_obj(raw, merged_env)


def get_target_config(
    targets_path: Path,
    *,
    target_name: str | None = None,
    env_file: Path | None = None,
) -> TargetConfig:
    data = load_targets_file(targets_path, env_file=env_file)
    name = target_name or data.get("default_target") or "main"
    targets = data.get("targets") or {}
    if name not in targets:
        raise KeyError(f"Target {name!r} not found in {targets_path}")

    entry = targets[name]
    ui_mode = entry.get("ui_mode", name if name in ("main", "portfolio") else "main")
    return TargetConfig(
        base_url=entry["base_url"],
        ui_mode=ui_mode,
        auth_login_mode=entry.get("auth_login_mode", "demo"),
        profile=entry.get("profile") or profile_for_mode(ui_mode),
        module=data.get("module", "unknown"),
        environment=data.get("environment", "preprod"),
    )
