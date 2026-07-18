from __future__ import annotations

from pathlib import Path
from typing import Any

from tools._shared.capability.plugin_base import CapabilityTool


class ChatTool(CapabilityTool):
    provider_env = 'CHAT_PROVIDER'
    default_provider = 'memory'
    allowed_providers = frozenset({'memory', 'cliq'})

    def build_adapter(self, provider: str) -> Any:
        if provider == 'cliq':
            from .adapters.cliq.adapter import Adapter
            return Adapter()
        if provider == 'memory':
            from .adapters.memory import MemoryAdapter
            return MemoryAdapter()
        raise ValueError(f'unknown provider {provider!r}')


def get_tool() -> ChatTool:
    return ChatTool(Path(__file__).resolve().parent)
