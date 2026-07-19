from __future__ import annotations

from pathlib import Path
from typing import Any

from tools._shared.capability.plugin_base import CapabilityTool


class DirectoryTool(CapabilityTool):
    provider_env = 'DIRECTORY_PROVIDER'
    default_provider = 'memory'
    allowed_providers = frozenset({'memory', 'openproject'})

    def build_adapter(self, provider: str) -> Any:
        if provider == 'openproject':
            from tools.directory.adapters.openproject.adapter import Adapter
            return Adapter()
        if provider == 'memory':
            from tools.directory.adapters.memory import MemoryAdapter
            return MemoryAdapter()
        raise ValueError(f'unknown provider {provider!r}')


def get_tool() -> DirectoryTool:
    return DirectoryTool(Path(__file__).resolve().parent)
