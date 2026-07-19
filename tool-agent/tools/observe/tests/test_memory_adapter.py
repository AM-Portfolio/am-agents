import pytest

from app.models.intent import IntentDocument
from tools.observe.plugin import get_tool


@pytest.mark.asyncio
async def test_memory_execute_roundtrip(monkeypatch):
    monkeypatch.setenv("OBSERVE_PROVIDER", "memory")
    tool = get_tool()
    result = await tool.execute(
        IntentDocument(
            backend=tool.name,
            operation="metrics.query",
            params={"query_ref": "up"},
            read_only=True,
            confidence=1.0,
        ),
        read_only=True,
        max_rows=10,
    )
    assert result["ok"] is True
    assert result["data"]["kind"] == "metrics"
