from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

from app.config import AGENT_ROOT, settings
from tools._shared.text import load_yaml_text, render_template

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    name: str
    content: str
    source: str
    version: str | None = None


class FilePromptProvider:
    def get(self, name: str, *, label: str, fallback_path: Path | None) -> PromptTemplate:
        if fallback_path and fallback_path.exists():
            return PromptTemplate(name=name, content=load_yaml_text(fallback_path), source="file")
        base_path = AGENT_ROOT / "app" / "prompts" / "base.yaml"
        if name.endswith("base") or name == "tool-agent/intent/base":
            return PromptTemplate(name=name, content=load_yaml_text(base_path), source="file")
        if fallback_path:
            logger.warning("prompt fallback missing for %s at %s", name, fallback_path)
        return PromptTemplate(name=name, content="", source="file")


class LangfusePromptProvider:
    def __init__(self) -> None:
        self._file_fallback = FilePromptProvider()
        self._cache: dict[tuple[str, str], tuple[float, PromptTemplate]] = {}

    def _auth_header(self) -> str | None:
        import base64

        if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
            return None
        token = f"{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}"
        return base64.b64encode(token.encode()).decode()

    def get(self, name: str, *, label: str, fallback_path: Path | None) -> PromptTemplate:
        cache_key = (name, label)
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < settings.TOOL_AGENT_PROMPT_CACHE_TTL_SECONDS:
            return cached[1]

        auth = self._auth_header()
        if not auth:
            return self._file_fallback.get(name, label=label, fallback_path=fallback_path)

        host = settings.LANGFUSE_HOST.rstrip("/")
        from urllib.parse import quote

        url = f"{host}/api/public/v2/prompts/{quote(name, safe='')}"
        try:
            resp = httpx.get(
                url,
                params={"label": label},
                headers={"Authorization": f"Basic {auth}"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                body = resp.json()
                prompt_text = body.get("prompt")
                if isinstance(prompt_text, list):
                    parts = [p.get("content", "") for p in prompt_text if isinstance(p, dict)]
                    content = "\n".join(parts).strip()
                else:
                    content = str(prompt_text or "").strip()
                template = PromptTemplate(
                    name=name,
                    content=content,
                    source="langfuse",
                    version=str(body.get("version")) if body.get("version") is not None else None,
                )
                self._cache[cache_key] = (now, template)
                return template
            logger.warning("Langfuse prompt fetch failed for %s [%s]", name, resp.status_code)
        except Exception as exc:
            logger.warning("Langfuse prompt fetch error for %s: %s", name, exc)

        return self._file_fallback.get(name, label=label, fallback_path=fallback_path)


def get_prompt_provider():
    if settings.PROMPT_SOURCE == "langfuse" and settings.LANGFUSE_ENABLED:
        return LangfusePromptProvider()
    return FilePromptProvider()


def compile_prompt(template: str, variables: dict[str, str]) -> str:
    return render_template(template, variables)
