"""Optional legacy loader for old widgetId catalogs (unused by chat path)."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger("am.fin.catalog")

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


def _catalog_path() -> Path:
    env = os.getenv("FINANCE_CATALOG_PATH")
    if env:
        return Path(env)
    # Historical path; file removed — returns empty map.
    here = Path(__file__).resolve()
    agents_root = here.parents[3]  # am-agents
    return agents_root / "catalog" / "finance" / "tools.yaml"


@lru_cache(maxsize=1)
def load_tool_widget_map() -> Dict[str, str]:
    """Legacy tool id -> widgetId; empty when catalog file is absent."""
    path = _catalog_path()
    if yaml is None or not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        tools = data.get("tools") or []
        out: Dict[str, str] = {}
        for t in tools:
            tid = t.get("id")
            wid = t.get("widgetId")
            if tid and wid:
                out[str(tid)] = str(wid)
        logger.info("Loaded finance catalog (%s tools) from %s", len(out), path)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load finance catalog: %s", exc)
        return {}


def catalog_priority_rows() -> List[Tuple[str, str, dict]]:
    """Rows for legacy intent_formatter; empty without a widgetId catalog file."""
    return [(tid, wid, {}) for tid, wid in load_tool_widget_map().items()]
