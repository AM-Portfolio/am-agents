from __future__ import annotations

import logging
import time
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)


class LlmCallResult(BaseModel):
    content: str
    model: str
    usage: dict[str, int] = Field(default_factory=dict)
    cost_usd: float | None = None
    latency_ms: int = 0
    gateway_trace_id: str | None = None


class LLMClient(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def routing(self) -> Literal["gateway", "direct"]: ...

    async def chat_with_usage(
        self,
        *,
        system: str,
        user: str,
        request_id: str,
        backend: str | None = None,
        generation_name: str = "tool-agent",
        temperature: float | None = None,
    ) -> LlmCallResult: ...

    async def health_check(self) -> bool: ...


class DirectLiteLLMClient:
    routing: Literal["gateway", "direct"] = "direct"

    def __init__(self) -> None:
        self.base_url = settings.LITELLM_BASE_URL.rstrip("/")
        self.api_key = settings.LITELLM_MASTER_KEY
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("LITELLM_MASTER_KEY is required for direct LLM calls")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat_with_usage(
        self,
        *,
        system: str,
        user: str,
        request_id: str,
        backend: str | None = None,
        generation_name: str = "tool-agent",
        temperature: float | None = None,
    ) -> LlmCallResult:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": settings.LLM_PLANNER_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "stream": False,
            "metadata": {
                "source": "tool-agent",
                "request_id": request_id,
                "generation_name": generation_name,
                "backend": backend,
            },
        }
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"LiteLLM failed [{resp.status_code}]: {resp.text[:500]}")
            data = resp.json()
        usage_raw = data.get("usage") or {}
        return LlmCallResult(
            content=data["choices"][0]["message"]["content"],
            model=str(data.get("model") or settings.LLM_PLANNER_MODEL),
            usage={
                "prompt_tokens": int(usage_raw.get("prompt_tokens") or 0),
                "completion_tokens": int(usage_raw.get("completion_tokens") or 0),
                "total_tokens": int(usage_raw.get("total_tokens") or 0),
            },
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.base_url}/health",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False


class GatewayLLMClient:
    routing: Literal["gateway", "direct"] = "gateway"

    def __init__(self) -> None:
        self.base_url = settings.MCP_GATEWAY_BASE_URL.rstrip("/")
        self.timeout = settings.LLM_TIMEOUT_SECONDS
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def available(self) -> bool:
        if settings.MCP_GATEWAY_AUTH_DISABLED:
            return True
        return bool(settings.AM_MCP_CLIENT_SECRET)

    async def _get_access_token(self) -> str | None:
        if settings.MCP_GATEWAY_AUTH_DISABLED:
            return None
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token
        if not settings.AM_MCP_CLIENT_SECRET or not settings.KEYCLOAK_TOKEN_URL:
            raise ValueError("Gateway auth requires AM_MCP_CLIENT_SECRET and KEYCLOAK_TOKEN_URL")
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

    async def chat_with_usage(
        self,
        *,
        system: str,
        user: str,
        request_id: str,
        backend: str | None = None,
        generation_name: str = "tool-agent",
        temperature: float | None = None,
    ) -> LlmCallResult:
        url = f"{self.base_url}/api/v1/agent/llm/completions"
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "model": settings.LLM_PLANNER_MODEL,
            "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "sessionId": request_id,
            "testId": request_id,
            "source": "tool-agent",
        }
        token = await self._get_access_token()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Gateway LLM failed [{resp.status_code}]: {resp.text[:500]}")
            data = resp.json()
        usage_raw = data.get("usage") or {}
        return LlmCallResult(
            content=data["content"],
            model=str(data.get("model") or settings.LLM_PLANNER_MODEL),
            usage={
                "prompt_tokens": int(usage_raw.get("prompt_tokens") or 0),
                "completion_tokens": int(usage_raw.get("completion_tokens") or 0),
                "total_tokens": int(usage_raw.get("total_tokens") or 0),
            },
            latency_ms=int((time.perf_counter() - started) * 1000),
            gateway_trace_id=data.get("traceId"),
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        if settings.LLM_ROUTING == "gateway":
            _llm_client = GatewayLLMClient()
        else:
            _llm_client = DirectLiteLLMClient()
    return _llm_client


def reset_llm_client() -> None:
    global _llm_client
    _llm_client = None
