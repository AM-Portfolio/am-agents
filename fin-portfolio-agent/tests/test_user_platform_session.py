"""Sprint D1 — user-platform HTTP client + RAM fallback."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from shared.clients.user_platform_client import UserPlatformClient
from shared.session.store import SessionStore


@pytest.fixture
def platform_settings(monkeypatch):
    from shared.core import config as config_mod

    monkeypatch.setattr(
        config_mod.settings, "USER_PLATFORM_URL", "http://user-platform.test"
    )
    monkeypatch.setattr(
        config_mod.settings,
        "USER_PLATFORM_SERVICE_TOKEN",
        "aaa.bbb.ccc",
    )
    monkeypatch.setattr(config_mod.settings, "USER_PLATFORM_TIMEOUT_SECONDS", 5.0)
    return config_mod.settings


def _json_response(status: int, payload: dict) -> httpx.Response:
    request = httpx.Request("GET", "http://user-platform.test/")
    return httpx.Response(status, json=payload, request=request)


@pytest.mark.asyncio
async def test_get_context_maps_messages(platform_settings):
    client = UserPlatformClient()
    session_id = str(uuid.uuid4())
    payload = {
        "data": {
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
                {"role": "system", "content": "skip"},
            ]
        }
    }
    mock_client = AsyncMock()
    mock_client.get.return_value = _json_response(200, payload)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("shared.clients.user_platform_client.httpx.AsyncClient", return_value=mock_client):
        rows = await client.get_context(session_id, "user-1", limit=10)

    assert rows == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    mock_client.get.assert_awaited()


@pytest.mark.asyncio
async def test_get_context_timeout_returns_none(platform_settings):
    client = UserPlatformClient()
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.TimeoutException("timeout")
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("shared.clients.user_platform_client.httpx.AsyncClient", return_value=mock_client):
        rows = await client.get_context(str(uuid.uuid4()), "user-1")

    assert rows is None


@pytest.mark.asyncio
async def test_append_messages_posts_body(platform_settings):
    client = UserPlatformClient()
    session_id = str(uuid.uuid4())
    mock_client = AsyncMock()
    mock_client.post.return_value = _json_response(201, {"data": []})
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("shared.clients.user_platform_client.httpx.AsyncClient", return_value=mock_client):
        ok = await client.append_messages(
            session_id,
            "user-1",
            [{"role": "user", "content": "Hi"}],
        )

    assert ok is True
    kwargs = mock_client.post.await_args.kwargs
    assert kwargs["json"]["product_id"] == "am_app"
    assert kwargs["json"]["agent_type"] == "fin_portfolio"
    assert kwargs["json"]["channel"] == "user_app"


@pytest.mark.asyncio
async def test_load_history_falls_back_to_ram_when_url_unset(monkeypatch):
    from shared.core import config as config_mod
    from shared.clients import user_platform_client as upc

    monkeypatch.setattr(config_mod.settings, "USER_PLATFORM_URL", "")
    store = SessionStore()
    store.clear_session("u1", "s1")
    store.append_turn("u1", "s1", "user", "ram only")

    history = await store.load_history("u1", "s1")
    assert history == [{"role": "user", "content": "ram only"}]
    assert upc.user_platform_client.enabled is False


@pytest.mark.asyncio
async def test_load_history_uses_remote_when_url_set(monkeypatch):
    from shared.clients.user_platform_client import user_platform_client
    from shared.core import config as config_mod

    monkeypatch.setattr(
        config_mod.settings, "USER_PLATFORM_URL", "http://user-platform.test"
    )
    store = SessionStore()
    sid = str(uuid.uuid4())
    store.clear_session("u1", sid)

    with patch.object(
        user_platform_client,
        "get_context",
        new=AsyncMock(return_value=[{"role": "user", "content": "from platform"}]),
    ):
        history = await store.load_history("u1", sid)

    assert history == [{"role": "user", "content": "from platform"}]


@pytest.mark.asyncio
async def test_persist_turn_noop_when_url_unset(monkeypatch):
    from shared.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "USER_PLATFORM_URL", "")
    store = SessionStore()
    with patch(
        "shared.session.store.user_platform_client.append_messages",
        new=AsyncMock(),
    ) as append:
        await store.persist_turn(
            "u1",
            str(uuid.uuid4()),
            [{"role": "user", "content": "x"}],
        )
        append.assert_not_awaited()
