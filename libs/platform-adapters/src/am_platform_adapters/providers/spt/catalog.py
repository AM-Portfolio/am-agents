"""File-backed TargetCatalog over catalog/spt/."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _default_catalog_root() -> Path:
    env = os.getenv("SPT_CATALOG_PATH", "").strip()
    if env:
        return Path(env)
    # .../am_platform_adapters/providers/spt/catalog.py → am-agents/
    here = Path(__file__).resolve()
    # providers/spt -> providers -> am_platform_adapters -> src -> platform-adapters -> libs -> am-agents
    return here.parents[6] / "catalog" / "spt"


class FileTargetCatalog:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or _default_catalog_root()
        self._entries: dict[str, dict[str, Any]] | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._entries is not None:
            return self._entries
        entries: dict[str, dict[str, Any]] = {}
        for sub in ("services", "flows"):
            folder = self._root / sub
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.yaml")):
                data = _load_yaml(path)
                tid = str(data.get("id") or path.stem)
                data["id"] = tid
                entries[tid] = data
        self._entries = entries
        return entries

    def list_services(self) -> list[dict[str, Any]]:
        return [dict(v) for v in self._load().values() if v.get("kind") == "service"]

    def get(self, *, target_id: str) -> dict[str, Any] | None:
        e = self._load().get(target_id)
        return dict(e) if e else None

    def list_all(self) -> list[dict[str, Any]]:
        return [dict(v) for v in self._load().values()]


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError(f"catalog entry must be mapping: {path}")
        return data
    except ImportError as exc:
        raise RuntimeError("PyYAML required for SPT catalog — pip install pyyaml") from exc
