from __future__ import annotations

import logging
import json
import time
import os
import asyncio
from typing import Any, AsyncIterator, Literal, Protocol, List, Dict, Optional

import httpx
from pydantic import BaseModel, Field

from shared.core.config import settings

logger = logging.getLogger(__name__)


class LlmCallResult(BaseModel):
    content: str
    model: str
    usage: dict[str, int] = Field(default_factory=dict)
    cost_usd: float | None = None
    latency_ms: int = 0
    gateway_trace_id: str | None = None


async def _emit_langfuse(
    prompt_key: str,
    messages: List[Dict[str, str]],
    output: str,
    model: str,
    error: str | None = None,
) -> None:
    if not settings.LANGFUSE_ENABLED:
        return
    pk = settings.LANGFUSE_PUBLIC_KEY
    sk = settings.LANGFUSE_SECRET_KEY
    host = settings.LANGFUSE_HOST.rstrip("/")
    if not pk or not sk or not host:
        logger.warning("LANGFUSE_ENABLED but public/secret keys or host are missing")
        return
    
    import base64
    import uuid
    from datetime import datetime, timezone
    
    auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    trace_id = str(uuid.uuid4())
    gen_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    max_chars = settings.LANGFUSE_TRACE_MAX_OUTPUT_CHARS
    
    # Format system/user inputs for Langfuse
    system = ""
    user = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            system = content
        else:
            user.append(f"{role.capitalize()}: {content}")
    user_str = "\n".join(user)
    
    meta = {
        "source": "fin-agent",
        "prompt_key": prompt_key,
    }
    
    batch = [
        {
            "id": str(uuid.uuid4()),
            "type": "trace-create",
            "timestamp": now,
            "body": {
                "id": trace_id,
                "name": f"llm.{prompt_key}",
                "userId": "fin-agent",
                "sessionId": trace_id,
                "tags": ["fin-agent", "llm", prompt_key],
                "metadata": meta,
                "input": {"system": system[:max_chars], "user": user_str[:max_chars]},
                "output": (error or output)[:max_chars],
            },
        },
        {
            "id": str(uuid.uuid4()),
            "type": "generation-create",
            "timestamp": now,
            "body": {
                "id": gen_id,
                "traceId": trace_id,
                "name": prompt_key,
                "model": model,
                "input": [
                    {"role": "system", "content": system[:max_chars]},
                    {"role": "user", "content": user_str[:max_chars]},
                ],
                "output": (error or output)[:max_chars],
                "metadata": meta,
                "level": "ERROR" if error else "DEFAULT",
                "statusMessage": error,
            },
        },
    ]
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{host}/api/public/ingestion",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {auth}",
                },
                json={"batch": batch}
            )
            if resp.status_code not in {200, 207}:
                logger.warning(f"Langfuse ingestion returned status {resp.status_code}")
    except Exception as e:
        logger.warning(f"Langfuse ingestion failed: {e}")


class DirectLiteLLMClient:
    routing: Literal["gateway", "direct"] = "direct"

    def __init__(self) -> None:
        base_url = settings.LITELLM_BASE_URL.strip() if settings.LITELLM_BASE_URL else ""
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        together_key = (settings.LITELLM_MASTER_KEY or settings.TOGETHER_API_KEY or "").strip()
        
        if not base_url:
            # Fall back to OpenRouter if key is present and together key is default/empty/expired
            if openrouter_key and (not together_key or together_key == "CHANGE_ME" or "bff39f3" in together_key):
                base_url = "https://openrouter.ai/api/v1"
                self.api_key = openrouter_key
            else:
                base_url = "https://api.together.ai/v1"
                self.api_key = together_key
        else:
            self.api_key = together_key
            
        self.base_url = base_url.rstrip("/")
        self.timeout = settings.LLM_TIMEOUT_SECONDS
        
        # Resolve Model
        self.model = settings.LLM_PLANNER_MODEL
        if "openrouter.ai" in self.base_url:
            self.model = "meta-llama/llama-3.3-70b-instruct"

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("LITELLM_MASTER_KEY or TOGETHER_API_KEY is required for direct LLM calls")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _metadata(self, *, request_id: str, generation_name: str, backend: str | None) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "generation_name": generation_name,
            "backend": backend,
            "source": "fin-agent",
        }

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        request_id: str = "fin-request",
    ) -> Any:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "stream": False,
            "metadata": self._metadata(request_id=request_id, generation_name="fin-agent", backend="finance"),
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code != 200:
                err_text = resp.text[:500]
                asyncio.create_task(_emit_langfuse("fin.chat", messages, "", self.model, err_text))
                raise RuntimeError(f"LiteLLM failed [{resp.status_code}]: {err_text}")
            data = resp.json()

        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        output_str = json.dumps(message.get("tool_calls")) if message.get("tool_calls") else content
        asyncio.create_task(_emit_langfuse("fin.chat", messages, output_str, self.model))

        if message.get("tool_calls"):
            return message
        return content

    async def chat_with_usage(
        self,
        *,
        system: str,
        user: str,
        request_id: str,
        backend: str | None = None,
        generation_name: str = "fin-agent",
        temperature: float | None = None,
    ) -> LlmCallResult:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        started = time.perf_counter()
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "stream": False,
            "metadata": self._metadata(request_id=request_id, generation_name=generation_name, backend=backend),
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code != 200:
                err_text = resp.text[:500]
                asyncio.create_task(_emit_langfuse(generation_name, messages, "", self.model, err_text))
                raise RuntimeError(f"LiteLLM failed [{resp.status_code}]: {err_text}")
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        asyncio.create_task(_emit_langfuse(generation_name, messages, content, self.model))

        usage_raw = data.get("usage") or {}
        return LlmCallResult(
            content=content,
            model=str(data.get("model") or self.model),
            usage={
                "prompt_tokens": int(usage_raw.get("prompt_tokens") or 0),
                "completion_tokens": int(usage_raw.get("completion_tokens") or 0),
                "total_tokens": int(usage_raw.get("total_tokens") or 0),
            },
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def chat_stream_with_usage(
        self,
        *,
        system: str,
        user: str,
        request_id: str,
        backend: str | None = None,
        generation_name: str = "fin-agent",
        temperature: float | None = None,
        on_token: Any | None = None,
    ) -> LlmCallResult:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "stream": True,
            "stream_options": {"include_usage": True},
            "metadata": self._metadata(request_id=request_id, generation_name=generation_name, backend=backend),
        }
        started = time.perf_counter()
        parts: list[str] = []
        usage_raw: dict[str, int] = {}
        model = self.model
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, headers=self._headers(), json=payload) as resp:
                if resp.status_code != 200:
                    err_text = f"LiteLLM stream status {resp.status_code}"
                    asyncio.create_task(_emit_langfuse(generation_name, messages, "", self.model, err_text))
                    raise RuntimeError(f"LiteLLM stream failed [{resp.status_code}]")
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if data.get("model"):
                        model = str(data["model"])
                    if data.get("usage"):
                        u = data["usage"]
                        usage_raw = {
                            "prompt_tokens": int(u.get("prompt_tokens") or 0),
                            "completion_tokens": int(u.get("completion_tokens") or 0),
                            "total_tokens": int(u.get("total_tokens") or 0),
                        }
                    delta = (data.get("choices") or [{}])[0].get("delta") or {}
                    token = delta.get("content")
                    if token:
                        parts.append(token)
                        if on_token:
                            await on_token(token)
        content = "".join(parts)
        asyncio.create_task(_emit_langfuse(generation_name, messages, content, model))

        return LlmCallResult(
            content=content,
            model=model,
            usage=usage_raw,
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

    def _headers(self, token: str | None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif not settings.MCP_GATEWAY_AUTH_DISABLED:
            raise ValueError("No gateway access token available")
        return headers

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        request_id: str = "fin-request",
    ) -> Any:
        url = f"{self.base_url}/api/v1/agent/llm/completions"
        payload = {
            "messages": messages,
            "model": settings.LLM_PLANNER_MODEL,
            "temperature": temperature,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "sessionId": request_id,
            "testId": request_id,
            "source": "fin-agent",
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=self._headers(token), json=payload)
            if resp.status_code != 200:
                err_text = resp.text[:500]
                asyncio.create_task(_emit_langfuse("fin.chat", messages, "", settings.LLM_PLANNER_MODEL, err_text))
                raise RuntimeError(f"Gateway LLM failed [{resp.status_code}]: {err_text}")
            data = resp.json()

        content = data.get("content") or ""
        output_str = json.dumps(data.get("tool_calls")) if data.get("tool_calls") else content
        asyncio.create_task(_emit_langfuse("fin.chat", messages, output_str, settings.LLM_PLANNER_MODEL))

        if data.get("tool_calls"):
            return data
        return content

    async def chat_with_usage(
        self,
        *,
        system: str,
        user: str,
        request_id: str,
        backend: str | None = None,
        generation_name: str = "fin-agent",
        temperature: float | None = None,
    ) -> LlmCallResult:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        started = time.perf_counter()
        url = f"{self.base_url}/api/v1/agent/llm/completions"
        payload = {
            "messages": messages,
            "model": settings.LLM_PLANNER_MODEL,
            "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "sessionId": request_id,
            "testId": request_id,
            "source": "fin-agent",
        }
        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=self._headers(token), json=payload)
            if resp.status_code != 200:
                err_text = resp.text[:500]
                asyncio.create_task(_emit_langfuse(generation_name, messages, "", settings.LLM_PLANNER_MODEL, err_text))
                raise RuntimeError(f"Gateway LLM failed [{resp.status_code}]: {err_text}")
            data = resp.json()

        content = data["content"]
        asyncio.create_task(_emit_langfuse(generation_name, messages, content, settings.LLM_PLANNER_MODEL))

        usage = data.get("usage") or {}
        return LlmCallResult(
            content=content,
            model=settings.LLM_PLANNER_MODEL,
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def chat_stream_with_usage(
        self,
        *,
        system: str,
        user: str,
        request_id: str,
        backend: str | None = None,
        generation_name: str = "fin-agent",
        temperature: float | None = None,
        on_token: Any | None = None,
    ) -> LlmCallResult:
        return await self.chat_with_usage(
            system=system,
            user=user,
            request_id=request_id,
            backend=backend,
            generation_name=generation_name,
            temperature=temperature,
        )

    async def health_check(self) -> bool:
        try:
            token = await self._get_access_token()
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.base_url}/health",
                    headers=self._headers(token),
                )
                return resp.status_code == 200
        except Exception:
            return False


class LLMClientWrapper:
    """Wrapper that resolves direct vs gateway routing and exposes a single singleton interface."""
    
    def __init__(self) -> None:
        self._client = None
        
    @property
    def client(self):
        if self._client is None:
            routing = settings.LLM_ROUTING.lower()
            if routing == "gateway":
                self._client = GatewayLLMClient()
            else:
                self._client = DirectLiteLLMClient()
        return self._client
        
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        request_id: str = "fin-request",
    ) -> Any:
        return await self.client.chat(
            messages=messages,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
            request_id=request_id,
        )

    async def chat_with_usage(self, **kwargs) -> LlmCallResult:
        return await self.client.chat_with_usage(**kwargs)

    async def chat_stream_with_usage(self, **kwargs) -> LlmCallResult:
        return await self.client.chat_stream_with_usage(**kwargs)

    async def health_check(self) -> bool:
        return await self.client.health_check()


llm_client = LLMClientWrapper()
