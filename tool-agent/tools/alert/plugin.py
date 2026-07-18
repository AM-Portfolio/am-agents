from __future__ import annotations

from pathlib import Path
from typing import Any

from tools._shared.capability.plugin_base import CapabilityTool


class AlertTool(CapabilityTool):
    provider_env = "ALERT_SILENCE_PROVIDER"
    default_provider = "memory"
    allowed_providers = frozenset({"memory", "grafana"})

    def build_adapter(self, provider: str) -> Any:
        if provider == "grafana":
            from .adapters.grafana import Adapter

            return Adapter()
        if provider == "memory":
            from .adapters.memory import MemoryAdapter

            return MemoryAdapter()
        raise ValueError(f"unknown provider {provider!r}")


def get_tool() -> AlertTool:
    return AlertTool(Path(__file__).resolve().parent)
