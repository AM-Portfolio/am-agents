"""LLM port implementations — gated until live provider is composed."""

from __future__ import annotations

import os
from typing import Any

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
    "complete_gated",
    "llm_enabled",
    "llm_status",
]
