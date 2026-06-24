from __future__ import annotations

from typing import Any, Protocol


class LLMClient(Protocol):
    async def chat_text(
        self,
        *,
        system: str,
        user: str,
        model: str,
        session_id: str,
        test_id: str,
        temperature: float | None = None,
    ) -> str: ...

    async def chat_vision(
        self,
        *,
        prompt: str,
        screenshot_base64: str,
        model: str,
        session_id: str,
        test_id: str,
    ) -> str: ...

    async def chat_completions(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        session_id: str,
        test_id: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]: ...
