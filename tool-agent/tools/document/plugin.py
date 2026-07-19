from __future__ import annotations

from pathlib import Path
from typing import Any

from tools._shared.capability.plugin_base import CapabilityTool


class DocumentTool(CapabilityTool):
    provider_env = 'DOCUMENT_PROVIDER'
    default_provider = 'memory'
    allowed_providers = frozenset({'memory', 'minio'})

    def build_adapter(self, provider: str) -> Any:
        if provider == 'minio':
            from .adapters.minio.adapter import Adapter
            return Adapter()
        if provider == 'memory':
            from .adapters.memory import MemoryAdapter
            return MemoryAdapter()
        raise ValueError(f'unknown provider {provider!r}')


def get_tool() -> DocumentTool:
    return DocumentTool(Path(__file__).resolve().parent)
