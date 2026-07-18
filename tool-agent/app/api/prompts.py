from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.config import AGENT_ROOT, settings
from app.prompts.builder import preview_intent_prompt
from app.prompts.provider import get_prompt_provider, reset_prompt_provider

router = APIRouter()


class PromptPreviewRequest(BaseModel):
    name: str | None = None
    label: str | None = None
    query: str | None = None
    backend: str | None = None
    god_mode: bool = False
    fallback: str | None = Field(
        default=None,
        description="Optional file path relative to tool-agent root for file-mode fallback",
    )

    @model_validator(mode="after")
    def require_name_or_query(self) -> PromptPreviewRequest:
        if not self.name and not self.query:
            raise ValueError("provide either name or query")
        return self


def _admin_enabled() -> None:
    if not settings.TOOL_AGENT_PROMPT_ADMIN_ENABLED:
        raise HTTPException(status_code=503, detail="Prompt admin endpoints disabled")


@router.post("/preview")
async def prompts_preview(body: PromptPreviewRequest) -> dict[str, Any]:
    _admin_enabled()
    if body.query:
        return preview_intent_prompt(body.query, body.backend, god_mode=body.god_mode)

    label = body.label or settings.langfuse_prompt_label()
    fallback_path: Path | None = None
    if body.fallback:
        candidate = Path(body.fallback)
        fallback_path = candidate if candidate.is_absolute() else (AGENT_ROOT / candidate)
    provider = get_prompt_provider()
    template = provider.get(body.name or "", label=label, fallback_path=fallback_path)
    age = None
    if template.cached_at is not None:
        age = round(time.time() - template.cached_at, 3)
    return {
        "name": template.name,
        "label": template.label or label,
        "content": template.content,
        "source": template.source,
        "version": template.version,
        "age_seconds": age,
        "prompt_source": settings.PROMPT_SOURCE,
        "langfuse_enabled": settings.LANGFUSE_ENABLED,
    }


@router.post("/reload")
async def prompts_reload() -> dict[str, Any]:
    _admin_enabled()
    provider = get_prompt_provider()
    cleared = provider.clear_cache()
    # Keep the singleton; only bust its cache. Reset is available for tests.
    return {
        "cleared": cleared,
        "prompt_source": settings.PROMPT_SOURCE,
        "langfuse_enabled": settings.LANGFUSE_ENABLED,
        "cache_ttl_seconds": settings.TOOL_AGENT_PROMPT_CACHE_TTL_SECONDS,
    }


@router.get("/cache")
async def prompts_cache() -> dict[str, Any]:
    _admin_enabled()
    provider = get_prompt_provider()
    return {
        "entries": provider.cache_entries(),
        "prompt_source": settings.PROMPT_SOURCE,
        "langfuse_enabled": settings.LANGFUSE_ENABLED,
        "cache_ttl_seconds": settings.TOOL_AGENT_PROMPT_CACHE_TTL_SECONDS,
    }


# Re-export for tests that want a hard reset after toggling settings.
__all__ = ["router", "reset_prompt_provider"]
