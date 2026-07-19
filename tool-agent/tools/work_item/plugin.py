from __future__ import annotations

from pathlib import Path
from typing import Any

from tools._shared.capability.plugin_base import CapabilityTool


class WorkItemTool(CapabilityTool):
    provider_env = 'WORK_ITEM_PROVIDER'
    default_provider = 'memory'
    allowed_providers = frozenset({'memory', 'openproject'})

    def build_adapter(self, provider: str) -> Any:
        if provider == 'openproject':
            from tools.work_item.adapters.openproject.adapter import Adapter
            return Adapter()
        if provider == 'memory':
            from tools.work_item.adapters.memory import MemoryAdapter
            return MemoryAdapter()
        raise ValueError(f'unknown provider {provider!r}')


def get_tool() -> WorkItemTool:
    return WorkItemTool(Path(__file__).resolve().parent)
