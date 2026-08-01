from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class LlmCompletion(BaseModel):
    text: str = ""
    model: str = ""
    gated: bool = False
    reason: str = ""
    prompt_key: str | None = None
    prompt_version: str | None = None
    prompt_source: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)


class LlmClient(Protocol):
    name: str

    def status(self) -> dict[str, Any]: ...

    async def complete(
        self,
        *,
        system: str,
        user: str,
        prompt_key: str | None = None,
        prompt_version: str | None = None,
        prompt_source: str | None = None,
    ) -> LlmCompletion: ...

    async def get_prompt_compiled(self, prompt_key: str, **kwargs: Any) -> str | None: ...
