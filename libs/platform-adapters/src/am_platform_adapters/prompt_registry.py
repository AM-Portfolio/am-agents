"""File-backed PromptRegistry over catalog/prompts/*.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _default_prompts_root() -> Path:
    env = os.getenv("PROMPT_CATALOG_PATH", "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    # prompt_registry.py → am_platform_adapters → src → platform-adapters → libs → am-agents
    return here.parents[4] / "catalog" / "prompts"


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML required for FilePromptRegistry") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


class FilePromptRegistry:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or _default_prompts_root()
        self._cache: dict[str, dict[str, Any]] | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        prompts: dict[str, dict[str, Any]] = {}
        if self._root.is_dir():
            for path in sorted(self._root.glob("*.yaml")):
                data = _load_yaml(path)
                for item in data.get("prompts") or []:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key") or "").strip()
                    if key:
                        prompts[key] = dict(item)
        self._cache = prompts
        return prompts

    def get(self, *, prompt_key: str, version: str | None = None) -> dict[str, Any]:
        prompts = self._load()
        if prompt_key not in prompts:
            raise KeyError(f"unknown prompt_key: {prompt_key}")
        entry = dict(prompts[prompt_key])
        if version and str(entry.get("version")) != str(version):
            raise KeyError(f"prompt {prompt_key} version {version} not found")
        return entry
