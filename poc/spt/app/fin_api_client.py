"""Optional HTTP client for fin-api-testing-agent (LLM payload fallback).

Off by default — SPT never imports that agent as a library.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def llm_suggest_payload(
    *,
    service: str,
    method: str,
    path: str,
    openapi_snippet: dict[str, Any] | None = None,
    error_hint: str | None = None,
) -> dict[str, Any]:
    """Call external agent once. Returns {ok, source, request?}."""
    if not settings.spt_payload_llm_fallback:
        return {"ok": False, "skipped": True, "reason": "llm_fallback_disabled"}
    base = (settings.spt_fin_api_testing_url or "").rstrip("/")
    if not base:
        return {"ok": False, "skipped": True, "reason": "fin_api_url_unset"}

    payload = {
        "service": service,
        "method": method,
        "path": path,
        "openapi": openapi_snippet or {},
        "error": error_hint,
    }
    url = f"{base}/v1/suggest-payload"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code >= 400:
            return {
                "ok": False,
                "source": "llm-fallback",
                "error": f"upstream_{resp.status_code}",
                "body": resp.text[:500],
            }
        data = resp.json()
        request = data.get("request") if isinstance(data, dict) else None
        if not isinstance(request, dict):
            return {"ok": False, "source": "llm-fallback", "error": "invalid_response"}
        return {"ok": True, "source": "llm-fallback", "request": request, "raw": data}
    except Exception as exc:
        logger.info("LLM payload fallback failed: %s", exc)
        return {"ok": False, "source": "llm-fallback", "error": str(exc)}
