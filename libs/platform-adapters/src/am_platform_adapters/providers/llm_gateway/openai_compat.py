"""OpenAI-compatible LlmPort adapter (lab)."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request


class OpenAICompatLlm:
    """Minimal chat completions client. Auth via env (SecretBroker later)."""

    def complete(self, *, prompt_key: str, variables: dict[str, Any], data_class: str = "internal") -> str:
        _ = data_class
        base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        api_key = os.getenv("LLM_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("LLM_API_KEY required for openai_compat")

        # Caller should pass rendered system/user in variables when using gateway;
        # fall back to dumping variables as user content.
        system = str(variables.get("system") or f"Prompt key: {prompt_key}. Reply with JSON only.")
        user = str(variables.get("user") or json.dumps(variables, default=str))
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
        }
        req = request.Request(
            f"{base}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise RuntimeError(f"LLM HTTP {exc.code}: {exc.read()[:200]!r}") from exc
        return str(payload["choices"][0]["message"]["content"])
