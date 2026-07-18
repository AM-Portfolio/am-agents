from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class ResolvedPrompt(BaseModel):
    key: str
    content: str
    source: str = "file"
    version: str | None = None
    label: str = ""
    variables: dict[str, str] = Field(default_factory=dict)


class PromptRegistry(Protocol):
    name: str

    def status(self) -> dict[str, Any]: ...

    def resolve(
        self,
        key: str,
        *,
        label: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> ResolvedPrompt: ...
