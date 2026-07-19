from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CapabilityParams(BaseModel):
    idempotency_key: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
