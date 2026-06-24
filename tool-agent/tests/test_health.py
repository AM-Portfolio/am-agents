import pytest


@pytest.mark.asyncio
async def test_health():
    from app.main import health

    body = await health()
    assert body["service"] == "tool-agent"
    assert body["status"] == "ok"
    assert "enabled_tools" in body


@pytest.mark.asyncio
async def test_ready():
    from app.main import ready

    body = await ready()
    assert "registry_loaded" in body


@pytest.mark.asyncio
async def test_plan_mongodb_rules():
    import httpx
    from httpx import ASGITransport

    from app.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v1/tools/plan",
            json={"query": "list mongo databases", "backend": "mongodb"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"]["backend"] == "mongodb"
    assert body["intent"]["operation"] == "list_databases"
