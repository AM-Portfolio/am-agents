from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LiteLLMClient:
    """Direct LiteLLM proxy calls — dev/fast path (skips gateway hop)."""

    def __init__(self) -> None:
        self.base_url = settings.LITELLM_BASE_URL.rstrip("/")
        self.api_key = settings.LITELLM_MASTER_KEY
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("LITELLM_MASTER_KEY is required when LLM_ROUTING=direct")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _metadata(self, *, session_id: str, test_id: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "test_id": test_id,
            "source": "ui-test-agent",
            "trace_user_id": "ui-test-agent",
        }

    async def chat_completions(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        session_id: str,
        test_id: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
            "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
            "stream": False,
            "metadata": self._metadata(session_id=session_id, test_id=test_id),
        }
        logger.debug("Direct LiteLLM request model=%s test_id=%s url=%s", model, test_id, url)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"LiteLLM failed [{resp.status_code}]: {resp.text[:500]}"
                )
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        return {
            "content": content,
            "model": model,
            "sessionId": session_id,
            "traceId": test_id,
            "usage": usage,
        }

    async def chat_text(
        self,
        *,
        system: str,
        user: str,
        model: str,
        session_id: str,
        test_id: str,
        temperature: float | None = None,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        body = await self.chat_completions(
            messages,
            model=model,
            session_id=session_id,
            test_id=test_id,
            temperature=temperature,
        )
        return body["content"]

    async def chat_vision(
        self,
        *,
        prompt: str,
        screenshot_base64: str,
        model: str,
        session_id: str,
        test_id: str,
    ) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"},
                    },
                ],
            }
        ]
        body = await self.chat_completions(
            messages,
            model=model,
            session_id=session_id,
            test_id=test_id,
            max_tokens=256,
        )
        return body["content"]
