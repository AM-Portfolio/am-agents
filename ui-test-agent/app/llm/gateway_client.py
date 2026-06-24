from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class GatewayLLMClient:
    """Routes LLM and vision calls through am-mcp-gateway → LiteLLM → Langfuse."""

    def __init__(self) -> None:
        self.base_url = settings.MCP_GATEWAY_BASE_URL.rstrip("/")
        self.timeout = settings.LLM_TIMEOUT_SECONDS
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_access_token(self) -> str | None:
        if settings.MCP_GATEWAY_AUTH_DISABLED:
            return None
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token
        if not settings.AM_MCP_CLIENT_SECRET:
            raise ValueError("AM_MCP_CLIENT_SECRET is required when gateway auth is enabled")

        data = {
            "grant_type": "client_credentials",
            "client_id": settings.AM_MCP_CLIENT_ID,
            "client_secret": settings.AM_MCP_CLIENT_SECRET,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(settings.KEYCLOAK_TOKEN_URL, data=data)
            resp.raise_for_status()
            body = resp.json()

        self._token = body["access_token"]
        self._token_expires_at = time.time() + int(body.get("expires_in", 300))
        return self._token

    def _headers(self, token: str | None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif not settings.MCP_GATEWAY_AUTH_DISABLED:
            raise ValueError("No gateway access token available")
        return headers

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
        url = f"{self.base_url}/api/v1/agent/llm/completions"
        payload = {
            "messages": messages,
            "model": model,
            "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
            "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
            "sessionId": session_id,
            "testId": test_id,
            "source": "ui-test-agent",
        }
        token = await self._get_access_token()
        logger.debug("Gateway LLM request model=%s test_id=%s", model, test_id)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=self._headers(token), json=payload)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Gateway LLM failed [{resp.status_code}]: {resp.text[:500]}"
                )
            return resp.json()

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
