"""Prompt registry — file primary with optional Langfuse (TTL + fallback)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx

from am_support_agent.ports.prompts import ResolvedPrompt


class FilePromptRegistry:
    name = "file-prompts"

    def __init__(self, *, root: Path | None = None) -> None:
        env_root = os.getenv("SUPPORT_AGENT_PROMPT_ROOT", "").strip()
        catalog = os.getenv("SUPPORT_AGENT_CATALOG_ROOT", "").strip()
        if root is not None:
            self.root = root
        elif env_root:
            self.root = Path(env_root)
        elif catalog:
            self.root = Path(catalog) / "prompts"
        else:
            self.root = Path("catalog/prompts")

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "wired": True,
            "root": str(self.root),
            "exists": self.root.exists(),
        }

    def resolve(
        self,
        key: str,
        *,
        label: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> ResolvedPrompt:
        path = self.root / f"{key}.md"
        if not path.exists():
            path = self.root / f"{key}.yaml"
        if not path.exists():
            path = self.root / key
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        for k, v in (variables or {}).items():
            content = content.replace(f"{{{{{k}}}}}", v)
        return ResolvedPrompt(
            key=key,
            content=content,
            source="file",
            label=label or "",
            variables=dict(variables or {}),
        )


class LangfusePromptRegistry:
    name = "langfuse-prompts"

    def __init__(self, *, fallback: FilePromptRegistry | None = None) -> None:
        self._fallback = fallback or FilePromptRegistry()
        self._cache: dict[tuple[str, str], tuple[float, ResolvedPrompt]] = {}
        self._ttl = float(os.getenv("SUPPORT_AGENT_PROMPT_CACHE_TTL_SECONDS", "60"))

    def status(self) -> dict[str, Any]:
        enabled = os.getenv("LANGFUSE_ENABLED", "").lower() in {"1", "true", "yes"}
        return {
            "name": self.name,
            "wired": enabled and bool(os.getenv("LANGFUSE_PUBLIC_KEY")),
            "host": os.getenv("LANGFUSE_HOST", ""),
            "cache_entries": len(self._cache),
            "fallback": self._fallback.status(),
        }

    def clear_cache(self) -> int:
        n = len(self._cache)
        self._cache.clear()
        return n

    def _auth(self) -> str | None:
        import base64

        pub = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        sec = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
        if not pub or not sec:
            return None
        return base64.b64encode(f"{pub}:{sec}".encode()).decode()

    def resolve(
        self,
        key: str,
        *,
        label: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> ResolvedPrompt:
        label = label or os.getenv("SUPPORT_AGENT_PROMPT_LABEL", "latest")
        cache_key = (key, label)
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < self._ttl:
            prompt = cached[1]
        else:
            auth = self._auth()
            host = (os.getenv("LANGFUSE_HOST") or "").rstrip("/")
            if not auth or not host or os.getenv("LANGFUSE_ENABLED", "").lower() not in {
                "1",
                "true",
                "yes",
            }:
                return self._fallback.resolve(key, label=label, variables=variables)
            from urllib.parse import quote

            try:
                resp = httpx.get(
                    f"{host}/api/public/v2/prompts/{quote(key, safe='')}",
                    params={"label": label},
                    headers={"Authorization": f"Basic {auth}"},
                    timeout=10.0,
                )
                if resp.status_code != 200:
                    return self._fallback.resolve(key, label=label, variables=variables)
                body = resp.json()
                text = body.get("prompt")
                if isinstance(text, list):
                    content = "\n".join(
                        p.get("content", "") for p in text if isinstance(p, dict)
                    ).strip()
                else:
                    content = str(text or "").strip()
                prompt = ResolvedPrompt(
                    key=key,
                    content=content,
                    source="langfuse",
                    version=str(body.get("version")) if body.get("version") is not None else None,
                    label=label,
                )
                self._cache[cache_key] = (now, prompt)
            except Exception:  # noqa: BLE001
                return self._fallback.resolve(key, label=label, variables=variables)

        content = prompt.content
        for k, v in (variables or {}).items():
            content = content.replace(f"{{{{{k}}}}}", v)
        return prompt.model_copy(update={"content": content, "variables": dict(variables or {})})
