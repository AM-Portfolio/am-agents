"""LLM port implementations — gated until live provider is composed."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from am_support_agent.ports.llm import LlmCompletion


def get_env_var(key_name: str, default: str = "") -> str:
    val = os.getenv(key_name)
    if val:
        return val
    try:
        for secret_file in ["/vault/secrets/am-agents-ops", "/vault/secrets/secrets"]:
            if os.path.exists(secret_file):
                with open(secret_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(f"export {key_name}=") or line.startswith(f"{key_name}="):
                            parts = line.split("=", 1)
                            if len(parts) == 2:
                                return parts[1].strip("\"'")
    except Exception:
        pass
    return default


def llm_enabled() -> bool:
    return get_env_var("SUPPORT_AGENT_LLM_ENABLED", "").lower() in {
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
            get_env_var("LITELLM_BASE_URL") or "http://localhost:4000"
        ).rstrip("/")
        self.api_key = get_env_var("LITELLM_MASTER_KEY") or ""
        self.model = (
            get_env_var("SUPPORT_AGENT_LLM_MODEL") or "together_ai/Prism-ML/Ternary-Bonsai-27B"
        )
        self.timeout = float(get_env_var("SUPPORT_AGENT_LLM_TIMEOUT", "60"))

        # Optional direct Langfuse client for client-side spans
        self._langfuse: Any = None
        self._init_langfuse()

    def _init_langfuse(self) -> None:
        """Try to initialise a Langfuse client for client-side trace emission."""
        try:
            from langfuse import Langfuse  # type: ignore

            public_key = get_env_var("LANGFUSE_PUBLIC_KEY", "")
            secret_key = get_env_var("LANGFUSE_SECRET_KEY", "")
            host = get_env_var("LANGFUSE_HOST", "http://localhost:3001")
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

        import uuid
        trace_id: str = str(uuid.uuid4())
        
        # Start a Langfuse generation span if client is available
        langfuse_generation: Any = None
        if self._langfuse is not None:
            try:
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

            # Ingest trace directly to Langfuse API for instant guaranteed observability
            try:
                pub_key = get_env_var("LANGFUSE_PUBLIC_KEY", "")
                sec_key = get_env_var("LANGFUSE_SECRET_KEY", "")
                host = (get_env_var("LANGFUSE_HOST") or "http://localhost:3001").rstrip("/")
                if pub_key and sec_key and trace_id:
                    import base64, uuid
                    from datetime import datetime, timezone
                    auth_b64 = base64.b64encode(f"{pub_key}:{sec_key}".encode()).decode()
                    now_str = datetime.now(timezone.utc).isoformat()
                    gen_id = str(uuid.uuid4())
                    
                    async with httpx.AsyncClient(timeout=5.0) as lf_client:
                        lf_res = await lf_client.post(
                            f"{host}/api/public/ingestion",
                            headers={
                                "Authorization": f"Basic {auth_b64}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "batch": [
                                    {
                                        "id": str(uuid.uuid4()),
                                        "type": "trace-create",
                                        "timestamp": now_str,
                                        "body": {
                                            "id": trace_id,
                                            "name": f"support_agent.{prompt_key or 'completion'}",
                                            "metadata": metadata,
                                        },
                                    },
                                    {
                                        "id": str(uuid.uuid4()),
                                        "type": "generation-create",
                                        "timestamp": now_str,
                                        "body": {
                                            "id": gen_id,
                                            "traceId": trace_id,
                                            "name": "litellm_completion",
                                            "model": model_used,
                                            "input": {"system": system, "user": user},
                                            "output": text,
                                            "usage": {
                                                "promptTokens": usage.get("prompt_tokens", 0),
                                                "completionTokens": usage.get("completion_tokens", 0),
                                                "totalTokens": usage.get("total_tokens", 0),
                                            },
                                            "metadata": {"latency_ms": latency_ms},
                                        },
                                    },
                                ]
                            },
                        )
                        import logging
                        logging.getLogger("support_agent.llm").info(
                            "Langfuse ingestion posted trace %s (HTTP %s)", trace_id, lf_res.status_code
                        )
            except Exception as exc:
                import logging
                logging.getLogger("support_agent.llm").warning("Langfuse direct ingestion failed: %s", exc)

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
