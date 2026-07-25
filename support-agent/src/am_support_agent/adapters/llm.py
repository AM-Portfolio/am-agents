"""LLM port implementations — gated until live provider is composed."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from am_support_agent.ports.llm import LlmCompletion


def llm_enabled() -> bool:
    return os.getenv("SUPPORT_AGENT_LLM_ENABLED", "").lower() in {
        "1",
        "true",
        "yes",
    }


class GatedLlmClient:
    """Default production-safe client: never calls a provider until wired."""

    name = "gated-llm"

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": llm_enabled(),
            "wired": False,
            "prefer": "compose HttpLlmClient or platform LlmPort when enabling live side effects",
            "redaction": "required before any prompt leave support-agent",
        }

    async def complete(
        self,
        *,
        system: str,
        user: str,
        prompt_key: str | None = None,
        prompt_version: str | None = None,
        prompt_source: str | None = None,
    ) -> LlmCompletion:
        _ = system, user
        status = self.status()
        reason = (
            "SUPPORT_AGENT_LLM_ENABLED is not set"
            if not status["enabled"]
            else "LLM composition root has no live provider wired"
        )
        return LlmCompletion(
            gated=True,
            reason=reason,
            prompt_key=prompt_key,
            prompt_version=prompt_version,
            prompt_source=prompt_source,
        )


class HttpLlmClient:
    """Live LLM client via LiteLLM proxy with Langfuse tracing.

    Activated when:
      SUPPORT_AGENT_LLM_PROVIDER=litellm
      LITELLM_BASE_URL=http://localhost:4000
      LITELLM_MASTER_KEY=sk-...
      SUPPORT_AGENT_LLM_MODEL=gemini-2.0-flash   (optional, default: gemini-2.0-flash)

    Langfuse traces are emitted automatically by LiteLLM when it is configured
    with LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST on the proxy side.
    We additionally log the trace_id as metadata so we can deep-link from incidents.
    """

    name = "http-litellm"

    def __init__(self) -> None:
        self.base_url = (
            os.getenv("LITELLM_BASE_URL") or "http://localhost:4000"
        ).rstrip("/")
        self.api_key = os.getenv("LITELLM_MASTER_KEY") or ""
        self.model = (
            os.getenv("SUPPORT_AGENT_LLM_MODEL") or "gemini-2.0-flash"
        )
        self.timeout = float(os.getenv("SUPPORT_AGENT_LLM_TIMEOUT", "60"))

        # Optional direct Langfuse client for client-side spans
        self._langfuse: Any = None
        self._init_langfuse()

    def _init_langfuse(self) -> None:
        """Try to initialise a Langfuse client for client-side trace emission."""
        try:
            from langfuse import Langfuse  # type: ignore

            public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
            secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
            host = os.getenv("LANGFUSE_HOST", "http://localhost:3001")
            if public_key and secret_key:
                self._langfuse = Langfuse(
                    public_key=public_key,
                    secret_key=secret_key,
                    host=host,
                )
        except Exception:
            pass  # langfuse not installed or misconfigured — skip client-side tracing

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": llm_enabled(),
            "wired": bool(self.api_key),
            "base_url": self.base_url,
            "model": self.model,
            "langfuse_client": self._langfuse is not None,
        }

    async def complete(
        self,
        *,
        system: str,
        user: str,
        prompt_key: str | None = None,
        prompt_version: str | None = None,
        prompt_source: str | None = None,
    ) -> LlmCompletion:
        if not self.api_key:
            return LlmCompletion(
                gated=True,
                reason="LITELLM_MASTER_KEY is not set",
                prompt_key=prompt_key,
                prompt_version=prompt_version,
                prompt_source=prompt_source,
            )

        # Build metadata for Langfuse trace tagging
        metadata: dict[str, Any] = {}
        if prompt_key:
            metadata["prompt_key"] = prompt_key
        if prompt_version:
            metadata["prompt_version"] = prompt_version
        if prompt_source:
            metadata["prompt_source"] = prompt_source

        # Start a Langfuse generation span if client is available
        langfuse_generation: Any = None
        trace_id: str = ""
        if self._langfuse is not None:
            try:
                import uuid
                trace_id = str(uuid.uuid4())
                trace = self._langfuse.trace(
                    id=trace_id,
                    name=f"support_agent.llm.{prompt_key or 'completion'}",
                    metadata=metadata,
                )
                langfuse_generation = trace.generation(
                    name="litellm_completion",
                    model=self.model,
                    input={"system": system, "user": user},
                    metadata=metadata,
                )
            except Exception:
                langfuse_generation = None

        start_ts = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload: dict[str, Any] = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.2,
                }
                if metadata:
                    payload["metadata"] = metadata

                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            msg = (
                data.get("choices", [{}])[0]
                .get("message", {})
            )
            # Some reasoning models return content=null but populate reasoning_content
            text = msg.get("content") or msg.get("reasoning_content") or ""
            model_used = data.get("model", self.model)
            usage = data.get("usage", {})
            latency_ms = int((time.time() - start_ts) * 1000)

            # Close Langfuse generation with output
            if langfuse_generation is not None:
                try:
                    langfuse_generation.end(
                        output=text,
                        usage={
                            "input": usage.get("prompt_tokens", 0),
                            "output": usage.get("completion_tokens", 0),
                            "total": usage.get("total_tokens", 0),
                        },
                        metadata={"latency_ms": latency_ms, "model": model_used},
                    )
                    self._langfuse.flush()
                except Exception:
                    pass

            return LlmCompletion(
                text=text,
                model=model_used,
                gated=False,
                prompt_key=prompt_key,
                prompt_version=prompt_version,
                prompt_source=prompt_source,
                usage={
                    **usage,
                    "latency_ms": latency_ms,
                    "langfuse_trace_id": trace_id,
                },
            )

        except Exception as exc:
            latency_ms = int((time.time() - start_ts) * 1000)
            if langfuse_generation is not None:
                try:
                    langfuse_generation.end(
                        output=f"ERROR: {exc}",
                        level="ERROR",
                        status_message=str(exc),
                    )
                    self._langfuse.flush()
                except Exception:
                    pass
            return LlmCompletion(
                gated=True,
                reason=f"LLM call failed: {exc}",
                prompt_key=prompt_key,
                prompt_version=prompt_version,
                prompt_source=prompt_source,
                usage={"latency_ms": latency_ms},
            )


class FakeLlmClient:
    """Deterministic test/dev LLM — never hits the network."""

    name = "fake-llm"

    def __init__(self, *, reply: str = "fake-completion") -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "enabled": True, "wired": True, "mode": "fake"}

    async def complete(
        self,
        *,
        system: str,
        user: str,
        prompt_key: str | None = None,
        prompt_version: str | None = None,
        prompt_source: str | None = None,
    ) -> LlmCompletion:
        self.calls.append({"system": system, "user": user, "prompt_key": prompt_key})
        return LlmCompletion(
            text=self.reply,
            model="fake",
            gated=False,
            prompt_key=prompt_key,
            prompt_version=prompt_version,
            prompt_source=prompt_source,
        )


def llm_status() -> dict[str, Any]:
    """Backward-compatible probe used by /v2/integrations before runtime is attached."""
    return GatedLlmClient().status()


async def complete_gated(prompt: str, **_: Any) -> dict[str, Any]:
    client = GatedLlmClient()
    result = await client.complete(system="", user=prompt)
    return {
        "gated": result.gated,
        "reason": result.reason,
        "prompt_chars": len(prompt),
        **client.status(),
    }


__all__ = [
    "FakeLlmClient",
    "GatedLlmClient",
    "HttpLlmClient",
    "complete_gated",
    "llm_enabled",
    "llm_status",
]
