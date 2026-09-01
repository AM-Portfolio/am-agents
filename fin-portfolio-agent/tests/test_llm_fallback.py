"""
tests/test_llm_fallback.py
Phase 0b — Unit tests for the 3-tier LLM fallback chain.

These tests use pytest-asyncio and unittest.mock; they do NOT hit any live API.
Run:  pytest tests/test_llm_fallback.py -v
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ok_response(model: str = "test-model", content: str = "hello") -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "model": model,
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _make_http_error(status: int, text: str = "err") -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://example.com/chat/completions")
    resp = httpx.Response(status, text=text, request=req)
    return httpx.HTTPStatusError(f"HTTP {status}", request=req, response=resp)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _silence_langfuse(monkeypatch):
    """Prevent any real Langfuse / network calls during tests."""
    async def _noop(*a, **kw):
        pass
    monkeypatch.setattr(
        "shared.llm.client._record_fin_langfuse", _noop
    )
    from shared.agents.token_budget import reset_turn_token_budget
    from shared.core.config import settings

    reset_turn_token_budget()
    settings.AI_MAX_TOKENS_PER_TURN = 0  # disable per-turn cap in LLM unit tests


@pytest.fixture()
def three_tier_chain(monkeypatch):
    """Patch _build_fallback_chain to return 3 tiers with dummy keys."""
    from shared.llm.client import TierSpec

    chain = [
        TierSpec(label="A", base_url="https://plan-a.example", model="model-a", api_key="key-a"),
        TierSpec(label="B", base_url="https://plan-b.example", model="model-b", api_key="key-b"),
        TierSpec(label="C", base_url="https://plan-c.example", model="model-c", api_key="key-c"),
    ]
    monkeypatch.setattr("shared.llm.client._build_fallback_chain", lambda: chain)
    return chain


# ---------------------------------------------------------------------------
# Test: Plan A succeeds immediately
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_a_success(three_tier_chain, monkeypatch):
    ok = _make_ok_response(model="model-a", content="portfolio is healthy")

    async def _success(**kw):
        assert kw["tier"].label == "A"
        return ok

    monkeypatch.setattr("shared.llm.client._attempt_completion", _success)

    from shared.llm.client import _call_with_fallback
    data, tier = await _call_with_fallback(
        messages=[{"role": "user", "content": "hi"}],
        request_id="test-001",
    )
    assert tier.label == "A"
    assert data["choices"][0]["message"]["content"] == "portfolio is healthy"


# ---------------------------------------------------------------------------
# Test: Plan A gets 429 twice -> falls back to Plan B
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_429_promotes_to_plan_b(three_tier_chain, monkeypatch):
    call_log: list[str] = []

    async def _flaky(**kw):
        label = kw["tier"].label
        call_log.append(label)
        if label == "A":
            raise _make_http_error(429)
        return _make_ok_response(model="model-b", content="from B")

    monkeypatch.setattr("shared.llm.client.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("shared.llm.client._attempt_completion", _flaky)

    from shared.llm.client import _call_with_fallback
    data, tier = await _call_with_fallback(
        messages=[{"role": "user", "content": "rate limited"}],
        request_id="test-429",
    )
    assert tier.label == "B"
    assert "A" in call_log
    assert "B" in call_log


# ---------------------------------------------------------------------------
# Test: Plan A 429 and Plan B 503 -> falls to Plan C
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_tiers_cascade(three_tier_chain, monkeypatch):
    call_log: list[str] = []

    async def _cascade(**kw):
        label = kw["tier"].label
        call_log.append(label)
        if label in ("A", "B"):
            raise _make_http_error(503, "service down")
        return _make_ok_response(model="model-c", content="from C")

    monkeypatch.setattr("shared.llm.client.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("shared.llm.client._attempt_completion", _cascade)

    from shared.llm.client import _call_with_fallback
    data, tier = await _call_with_fallback(
        messages=[{"role": "user", "content": "all failing"}],
        request_id="test-cascade",
    )
    assert tier.label == "C"
    assert call_log.count("A") >= 1
    assert call_log.count("B") >= 1
    assert call_log.count("C") == 1


# ---------------------------------------------------------------------------
# Test: All 3 tiers fail -> FallbackLLMError raised with traceId
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_tiers_exhausted_raises(three_tier_chain, monkeypatch):
    async def _always_fail(**kw):
        raise _make_http_error(500, "internal error")

    monkeypatch.setattr("shared.llm.client.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("shared.llm.client._attempt_completion", _always_fail)

    from shared.llm.client import _call_with_fallback, FallbackLLMError
    with pytest.raises(FallbackLLMError) as exc_info:
        await _call_with_fallback(
            messages=[{"role": "user", "content": "all down"}],
            request_id="test-all-fail",
        )

    err = exc_info.value
    assert err.trace_id == "test-all-fail"
    assert len(err.tier_errors) == 3
    assert "Plan A" in err.tier_errors[0]
    assert "Plan B" in err.tier_errors[1]
    assert "Plan C" in err.tier_errors[2]


# ---------------------------------------------------------------------------
# Test: Timeout promotes immediately (no retry within tier)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_promotes_immediately(three_tier_chain, monkeypatch):
    call_log: list[str] = []

    async def _timeout_a(**kw):
        label = kw["tier"].label
        call_log.append(label)
        if label == "A":
            raise asyncio.TimeoutError()
        return _make_ok_response(model="model-b")

    monkeypatch.setattr("shared.llm.client.asyncio.sleep", AsyncMock())
    async def _patched_wait_for(coro, timeout=None):
        return await coro
    monkeypatch.setattr("shared.llm.client.asyncio.wait_for", _patched_wait_for)
    monkeypatch.setattr("shared.llm.client._attempt_completion", _timeout_a)

    from shared.llm.client import _call_with_fallback
    data, tier = await _call_with_fallback(
        messages=[{"role": "user", "content": "slow"}],
        request_id="test-timeout",
    )
    assert tier.label == "B"
    assert call_log.count("A") == 1


# ---------------------------------------------------------------------------
# Test: Auth error (401) promotes without retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_error_promotes_without_retry(three_tier_chain, monkeypatch):
    call_log: list[str] = []

    async def _auth_fail(**kw):
        label = kw["tier"].label
        call_log.append(label)
        if label == "A":
            raise _make_http_error(401, "unauthorized")
        return _make_ok_response(model="model-b")

    monkeypatch.setattr("shared.llm.client.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("shared.llm.client._attempt_completion", _auth_fail)

    from shared.llm.client import _call_with_fallback
    data, tier = await _call_with_fallback(
        messages=[{"role": "user", "content": "auth fail"}],
        request_id="test-auth",
    )
    assert tier.label == "B"
    assert call_log.count("A") == 1


# ---------------------------------------------------------------------------
# Test: DirectLiteLLMClient.chat returns ERROR dict (not crash) when all fail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_direct_client_chat_returns_error_dict(monkeypatch):
    from shared.llm.client import FallbackLLMError

    async def _raise_fallback(**kw):
        raise FallbackLLMError(trace_id="test-err-dict", tier_errors=["A: down", "B: down", "C: down"])

    monkeypatch.setattr("shared.llm.client._call_with_fallback", _raise_fallback)

    from shared.llm.client import DirectLiteLLMClient
    client = DirectLiteLLMClient()
    result = await client.chat([{"role": "user", "content": "hi"}], request_id="test-err")

    assert isinstance(result, dict)
    assert result["error"] is True
    assert result["traceId"] == "test-err-dict"
    assert "message" in result
