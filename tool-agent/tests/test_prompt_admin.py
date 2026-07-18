import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_prompt_preview_by_name():
    from app.main import app
    from app.prompts.provider import reset_prompt_provider

    reset_prompt_provider()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v1/prompts/preview",
            json={"name": "tool-agent/intent/base"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "file"
    assert body["content"]
    assert body["name"] == "tool-agent/intent/base"


@pytest.mark.asyncio
async def test_prompt_preview_by_query():
    from app.main import app
    from app.prompts.provider import reset_prompt_provider

    reset_prompt_provider()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v1/prompts/preview",
            json={"query": "list mongo databases", "backend": "mongodb"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prompt"]
    assert "snippets" in body
    assert body["candidates"] == ["mongodb"]


@pytest.mark.asyncio
async def test_prompt_reload_and_cache():
    from app.main import app
    from app.prompts.provider import get_prompt_provider, reset_prompt_provider

    reset_prompt_provider()
    provider = get_prompt_provider()
    # Warm file provider is a no-op cache; reload still returns cleared count.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        reload_resp = await client.post("/api/v1/prompts/reload")
        cache_resp = await client.get("/api/v1/prompts/cache")
    assert reload_resp.status_code == 200
    assert "cleared" in reload_resp.json()
    assert cache_resp.status_code == 200
    assert cache_resp.json()["entries"] == []
    assert provider.cache_entries() == []


@pytest.mark.asyncio
async def test_prompt_admin_disabled(monkeypatch):
    from app.config import settings
    from app.main import app
    from app.prompts.provider import reset_prompt_provider

    monkeypatch.setattr(settings, "TOOL_AGENT_PROMPT_ADMIN_ENABLED", False)
    reset_prompt_provider()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        preview = await client.post("/api/v1/prompts/preview", json={"name": "tool-agent/intent/base"})
        reload = await client.post("/api/v1/prompts/reload")
        cache = await client.get("/api/v1/prompts/cache")
    assert preview.status_code == 503
    assert reload.status_code == 503
    assert cache.status_code == 503
