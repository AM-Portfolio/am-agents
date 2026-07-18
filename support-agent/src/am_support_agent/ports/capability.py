from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from am_support_agent.contracts.capabilities import CapabilityCall


class CapabilityResult(BaseModel):
    ok: bool = True
    capability: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    plan_hash: str | None = None
    provider: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class CapabilityClient(Protocol):
    """Generic tool-agent capability surface (work-item.*, chat.*, …)."""

    name: str

    def status(self) -> dict[str, Any]: ...

    async def call(self, call: CapabilityCall) -> CapabilityResult: ...
