from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "db-agent"


@pytest.mark.asyncio
async def test_query_rule_based_qdrant_mock():
    mock_data = {"collections": [{"name": "ui_patterns"}]}

    with patch("app.nodes.execute_tool.run_adapter", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_data
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/db/query",
                json={
                    "query": "list qdrant collections",
                    "include_summary": False,
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "qdrant"
    assert body["operation"] == "list_collections"
    assert body["data"]["collections"][0]["name"] == "ui_patterns"
