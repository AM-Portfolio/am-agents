"""OpenAI-compatible / LiteLLM LlmPort + optional Langfuse ingestion."""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib import error, request

LOG = logging.getLogger("am_platform_adapters.llm")


def _llm_base_url() -> str:
    # Prefer LiteLLM (db-agent / ui-test-agent style) then generic OpenAI-compat
    litellm = os.getenv("LITELLM_BASE_URL", "").strip()
    if litellm:
        return litellm.rstrip("/")
    return os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def _llm_api_key() -> str:
    return (
        os.getenv("LLM_API_KEY", "").strip()
        or os.getenv("LITELLM_MASTER_KEY", "").strip()
    )


def _llm_model() -> str:
    return (
        os.getenv("LLM_MODEL", "").strip()
        or os.getenv("LLM_PLANNER_MODEL", "").strip()
        or "gpt-4o-mini"
    )


def _langfuse_enabled() -> bool:
    return os.getenv("LANGFUSE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _emit_langfuse(
    *,
    prompt_key: str,
    model: str,
    system: str,
    user: str,
    output: str,
    error: str | None = None,
) -> None:
    if not _langfuse_enabled():
        return
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = os.getenv("LANGFUSE_HOST", "https://langfuse.munish.org").rstrip("/")
    if not pk or not sk:
        LOG.warning("LANGFUSE_ENABLED but keys missing — skip trace")
        return
    auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    trace_id = str(uuid.uuid4())
    gen_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    max_chars = int(os.getenv("LANGFUSE_TRACE_MAX_OUTPUT_CHARS", "8000"))
    meta = {
        "source": "platform-worker",
        "prompt_key": prompt_key,
        "service": "agent-platform",
    }
    batch = [
        {
            "id": str(uuid.uuid4()),
            "type": "trace-create",
            "timestamp": now,
            "body": {
                "id": trace_id,
                "name": f"llm.{prompt_key}",
                "userId": "platform-worker",
                "sessionId": trace_id,
                "tags": ["agent-platform", "llm", prompt_key],
                "metadata": meta,
                "input": {"system": system[:max_chars], "user": user[:max_chars]},
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
                    {"role": "user", "content": user[:max_chars]},
                ],
                "output": (error or output)[:max_chars],
                "metadata": meta,
                "level": "ERROR" if error else "DEFAULT",
                "statusMessage": error,
            },
        },
    ]
    req = request.Request(
        f"{host}/api/public/ingestion",
        data=json.dumps({"batch": batch}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=10) as resp:
            if resp.status not in {200, 207}:
                LOG.warning("Langfuse ingestion HTTP %s", resp.status)
    except Exception as exc:  # noqa: BLE001 — tracing must not break LLM path
        LOG.warning("Langfuse ingestion failed: %s", exc)


class OpenAICompatLlm:
    """LiteLLM / OpenAI-compatible chat completions (+ Langfuse when enabled)."""

    def complete(self, *, prompt_key: str, variables: dict[str, Any], data_class: str = "internal") -> str:
        _ = data_class
        base = _llm_base_url()
        model = _llm_model()
        api_key = _llm_api_key()
        if not api_key:
            raise RuntimeError("LLM_API_KEY or LITELLM_MASTER_KEY required")

        system = str(variables.get("system") or f"Prompt key: {prompt_key}. Reply with JSON only.")
        user = str(variables.get("user") or json.dumps(variables, default=str))
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            # Helps LiteLLM → Langfuse callback on the proxy when configured
            "metadata": {
                "source": "platform-worker",
                "prompt_key": prompt_key,
                "trace_user_id": "platform-worker",
            },
        }
        # LiteLLM often exposes /chat/completions; OpenAI uses /v1/chat/completions
        url = f"{base}/chat/completions"
        if base.endswith("/v1"):
            url = f"{base}/chat/completions"
        elif "/v1" not in base and "openai.com" in base:
            url = f"{base}/v1/chat/completions"

        req = request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            content = str(payload["choices"][0]["message"]["content"])
            _emit_langfuse(
                prompt_key=prompt_key,
                model=model,
                system=system,
                user=user,
                output=content,
            )
            return content
        except error.HTTPError as exc:
            err_body = exc.read()[:500]
            msg = f"LLM HTTP {exc.code}: {err_body!r}"
            _emit_langfuse(
                prompt_key=prompt_key,
                model=model,
                system=system,
                user=user,
                output="",
                error=msg,
            )
            raise RuntimeError(msg) from exc
