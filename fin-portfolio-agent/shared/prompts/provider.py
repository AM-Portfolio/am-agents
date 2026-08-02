"""Prompt provider: Langfuse | file with fail-open cache → file fallback."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from shared.core.config import settings

logger = logging.getLogger(__name__)

AGENT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYSTEM_PROMPT_PATH = AGENT_ROOT / "prompts" / "fin_agent_system.md"
PROMPT_NAME_SYSTEM = "fin-agent/system"


@dataclass
class PromptTemplate:
    name: str
    content: str
    source: str
    version: Optional[str] = None
    label: Optional[str] = None
    cached_at: Optional[float] = None
    langfuse_prompt: Any = None  # SDK prompt object for generation linking


class PromptProvider(Protocol):
    def get(
        self, name: str, *, label: str, fallback_path: Path | None
    ) -> PromptTemplate: ...

    def clear_cache(self) -> int: ...


class FilePromptProvider:
    def get(
        self, name: str, *, label: str, fallback_path: Path | None
    ) -> PromptTemplate:
        path = fallback_path or DEFAULT_SYSTEM_PROMPT_PATH
        content = ""
        if path and path.exists():
            content = path.read_text(encoding="utf-8").strip()
        else:
            logger.warning("prompt file missing for %s at %s", name, path)
        return PromptTemplate(
            name=name,
            content=content,
            source="file",
            label=label,
            cached_at=time.time(),
        )

    def clear_cache(self) -> int:
        return 0


class LangfusePromptProvider:
    """Langfuse → TTL cache → file fallback."""

    def __init__(self) -> None:
        self._file_fallback = FilePromptProvider()
        self._cache: dict[tuple[str, str], tuple[float, PromptTemplate]] = {}

    def clear_cache(self) -> int:
        n = len(self._cache)
        self._cache.clear()
        return n

    def get(
        self, name: str, *, label: str, fallback_path: Path | None
    ) -> PromptTemplate:
        cache_key = (name, label)
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < settings.PROMPT_CACHE_TTL_SECONDS:
            return cached[1]

        if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
            return self._file_fallback.get(name, label=label, fallback_path=fallback_path)

        try:
            from langfuse import Langfuse

            client = Langfuse(
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
                host=settings.LANGFUSE_HOST,
            )
            lf_prompt = client.get_prompt(name, label=label)
            content = ""
            if hasattr(lf_prompt, "compile"):
                try:
                    content = str(lf_prompt.compile()).strip()
                except Exception:  # noqa: BLE001
                    content = ""
            if not content:
                raw = getattr(lf_prompt, "prompt", None)
                if isinstance(raw, list):
                    parts = [p.get("content", "") for p in raw if isinstance(p, dict)]
                    content = "\n".join(parts).strip()
                else:
                    content = str(raw or "").strip()
            version = None
            if getattr(lf_prompt, "version", None) is not None:
                version = str(lf_prompt.version)
            template = PromptTemplate(
                name=name,
                content=content or self._file_fallback.get(
                    name, label=label, fallback_path=fallback_path
                ).content,
                source="langfuse" if content else "file",
                version=version,
                label=label,
                cached_at=now,
                langfuse_prompt=lf_prompt if content else None,
            )
            self._cache[cache_key] = (now, template)
            return template
        except Exception as exc:  # noqa: BLE001
            logger.warning("Langfuse prompt fetch failed for %s (fallback file): %s", name, exc)
            return self._file_fallback.get(name, label=label, fallback_path=fallback_path)


_provider: PromptProvider | None = None
_provider_key: tuple[str, bool] | None = None


def get_prompt_provider() -> PromptProvider:
    global _provider, _provider_key
    key = (settings.PROMPT_SOURCE, bool(settings.LANGFUSE_ENABLED))
    if _provider is None or _provider_key != key:
        if settings.PROMPT_SOURCE == "langfuse" and settings.LANGFUSE_ENABLED:
            _provider = LangfusePromptProvider()
        else:
            _provider = FilePromptProvider()
        _provider_key = key
    return _provider


def reset_prompt_provider() -> None:
    global _provider, _provider_key
    if _provider is not None:
        _provider.clear_cache()
    _provider = None
    _provider_key = None


def get_system_prompt() -> PromptTemplate:
    return get_prompt_provider().get(
        PROMPT_NAME_SYSTEM,
        label=settings.PROMPT_LABEL,
        fallback_path=DEFAULT_SYSTEM_PROMPT_PATH,
    )
