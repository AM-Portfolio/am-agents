"""Google Gemini LlmPort adapter (direct API — vault GEMINI_API_KEY)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import error, request

from am_platform_adapters.providers.llm_gateway.openai_compat import _emit_langfuse

LOG = logging.getLogger("am_platform_adapters.llm.gemini")


class GeminiLlm:
    """Direct Gemini generateContent — used when LiteLLM upstream keys are unavailable."""

    def complete(self, *, prompt_key: str, variables: dict[str, Any], data_class: str = "internal") -> str:
        _ = data_class
        api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY required for LLM_PROVIDER=gemini")
        model = (
            os.getenv("LLM_MODEL", "").strip()
            or os.getenv("GEMINI_MODEL", "").strip()
            or "gemini-2.0-flash"
        )
        if model.startswith("models/"):
            model = model[len("models/") :]

        system = str(variables.get("system") or f"Prompt key: {prompt_key}. Reply with JSON only.")
        user = str(variables.get("user") or json.dumps(variables, default=str))
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.1},
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={api_key}"
        )
        req = request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            parts = (
                (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts"))
                or []
            )
            content = "".join(str(p.get("text") or "") for p in parts)
            if not content:
                raise RuntimeError(f"empty Gemini response: {str(payload)[:300]}")
            _emit_langfuse(
                prompt_key=prompt_key,
                model=model,
                system=system,
                user=user,
                output=content,
            )
            return content
        except error.HTTPError as exc:
            msg = f"Gemini HTTP {exc.code}: {exc.read()[:400]!r}"
            _emit_langfuse(
                prompt_key=prompt_key,
                model=model,
                system=system,
                user=user,
                output="",
                error=msg,
            )
            raise RuntimeError(msg) from exc
