from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.intent_schema import DbExecuteRequest, IntentDocument
from app.llm_client import LlmCallResult, reset_llm_client


@pytest.mark.asyncio
async def test_gateway_llm_client_chat():
    reset_llm_client()
    from app.config import settings
    from app.llm_client import GatewayLLMClient

    settings.MCP_GATEWAY_AUTH_DISABLED = True
    client = GatewayLLMClient()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "content": '{"backend":"qdrant","operation":"list_collections","params":{},"read_only":true,"confidence":0.9,"rationale":"ok"}',
        "model": "test-model",
        "traceId": "gw-trace-1",
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await client.chat_with_usage(
            system="sys",
            user="list collections",
            request_id="req-1",
        )

    assert result.gateway_trace_id == "gw-trace-1"
    assert "qdrant" in result.content


@pytest.mark.asyncio
async def test_execute_entity_portfolio():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    mock_data = {"documents": [{"_id": "163d0143-4fcb-480c-ac20-622f14e0e293", "name": "Test"}]}

    with patch("app.nodes.execute_tool.run_adapter", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_data
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/db/execute",
                json={
                    "intent": {
                        "backend": "mongodb",
                        "operation": "find",
                        "params": {
                            "entity": "portfolio",
                            "id": "163d0143-4fcb-480c-ac20-622f14e0e293",
                        },
                        "read_only": True,
                        "confidence": 1.0,
                        "rationale": "entity lookup",
                    },
                    "include_summary": False,
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["entity"] == "portfolio"
    assert body["resolved_params"]["database"] == "portfolio"
    assert body["resolved_params"]["collection"] == "portfolios"
    assert body["resolved_params"]["filter"]["_id"] == "163d0143-4fcb-480c-ac20-622f14e0e293"


@pytest.mark.asyncio
async def test_execute_structured():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    intent = IntentDocument(
        backend="qdrant",
        operation="list_collections",
        params={},
        confidence=1.0,
        rationale="structured test",
    )
    mock_data = {"collections": [{"name": "ui_patterns"}]}

    with patch("app.nodes.execute_tool.run_adapter", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_data
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/db/execute",
                json={"intent": intent.model_dump(), "include_summary": False},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["parse_source"] == "structured"
    assert body["operation"] == "list_collections"


@pytest.mark.asyncio
async def test_plan_endpoint():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/db/plan",
            json={"query": "list qdrant collections", "read_only": True},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"]["backend"] == "qdrant"
    assert body["would_execute"] == "qdrant.list_collections"
