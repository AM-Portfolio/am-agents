from __future__ import annotations

from pathlib import Path
from typing import Any

from tools._shared.capability.plugin_base import CapabilityTool


class SPTTool(CapabilityTool):
    provider_env = 'SPT_PROVIDER'
    default_provider = 'memory'
    allowed_providers = frozenset({'memory', 'k6'})

    def build_adapter(self, provider: str) -> Any:
        if provider == 'k6':
            from .adapters.k6.adapter import Adapter
            return Adapter()
        if provider == 'memory':
            from .adapters.memory import MemoryAdapter
            return MemoryAdapter()
        raise ValueError(f'unknown provider {provider!r}')


def get_tool() -> SPTTool:
    return SPTTool(Path(__file__).resolve().parent)
