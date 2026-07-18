from __future__ import annotations

from pathlib import Path
from typing import Any

from tools._shared.capability.plugin_base import CapabilityTool


class MailTool(CapabilityTool):
    provider_env = 'MAIL_PROVIDER'
    default_provider = 'memory'
    allowed_providers = frozenset({'memory', 'zoho'})

    def build_adapter(self, provider: str) -> Any:
        if provider == 'zoho':
            from .adapters.zoho.adapter import Adapter
            return Adapter()
        if provider == 'memory':
            from .adapters.memory import MemoryAdapter
            return MemoryAdapter()
        raise ValueError(f'unknown provider {provider!r}')


def get_tool() -> MailTool:
    return MailTool(Path(__file__).resolve().parent)
