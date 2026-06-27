import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_plan_stream_returns_sse_events():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/api/v1/tools/plan/stream",
            json={"query": "list kafka topics", "backend": "kafka", "read_only": True},
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            body = ""
            async for chunk in resp.aiter_text():
                body += chunk
            assert "parse_intent" in body
            assert '"event": "done"' in body or '"event":"done"' in body
