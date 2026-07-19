"""Read-only catalog access for procedural memory (prompts / verify / spt).

Reads from the monorepo `catalog/` tree until a promotion process owns writes.
Does not modify catalog files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_catalog_root() -> Path:
    env = os.getenv("SUPPORT_AGENT_CATALOG_ROOT", "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "catalog"
        if candidate.is_dir() and (candidate / "prompts").exists():
            return candidate
        # Walk from package → support-agent → monorepo
        sibling = parent.parent / "catalog"
        if sibling.is_dir() and (sibling / "prompts").exists():
            return sibling
    # Fallback: monorepo-relative guess from source layout
    try:
        return here.parents[4] / "catalog"
    except IndexError:
        return Path("catalog")


class CatalogReader:
    """Procedural memory reader — prompts, verify checks, SPT definitions."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_catalog_root()

    @classmethod
    def from_env(cls) -> CatalogReader:
        return cls(default_catalog_root())

    def available(self) -> bool:
        return self.root.is_dir()

    def _load_dir(self, relative: str) -> list[dict[str, Any]]:
        base = self.root / relative
        if not base.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".json", ".yaml", ".yml", ".md", ".txt"}:
                continue
            entry: dict[str, Any] = {
                "id": path.stem,
                "name": path.name,
                "path": str(path.relative_to(self.root)).replace("\\", "/"),
                "kind": relative,
            }
            if path.suffix.lower() == ".json":
                try:
                    entry["data"] = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    entry["data_error"] = "unreadable_json"
            out.append(entry)
        return out

    def list_prompts(self) -> list[dict[str, Any]]:
        return self._load_dir("prompts")

    def list_verify(self) -> list[dict[str, Any]]:
        return self._load_dir("verify")

    def list_spt(self) -> list[dict[str, Any]]:
        return self._load_dir("spt")

    def summary(self) -> dict[str, Any]:
        return {
            "catalog_root": str(self.root),
            "available": self.available(),
            "prompts": len(self.list_prompts()),
            "verify": len(self.list_verify()),
            "spt": len(self.list_spt()),
            "write_policy": "read_only_until_promotion_gate",
        }


__all__ = ["CatalogReader", "default_catalog_root"]
