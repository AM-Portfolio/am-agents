import pytest

from app.models.intent import IntentDocument
from tools.document.plugin import get_tool


@pytest.mark.asyncio
async def test_memory_execute_roundtrip(monkeypatch):
    monkeypatch.setenv("DOCUMENT_PROVIDER", "memory")
    monkeypatch.setenv("TOOL_AGENT_ALLOW_WRITES", "true")
    tool = get_tool()
    put = await tool.execute(
        IntentDocument(
            backend=tool.name,
            operation="put",
            params={"object_key": "a/b.txt", "content": "hi", "idempotency_key": "d1"},
            read_only=False,
            confidence=1.0,
        ),
        read_only=False,
        max_rows=10,
    )
    assert put["ok"] is True
    exists = await tool.execute(
        IntentDocument(
            backend=tool.name,
            operation="exists",
            params={"object_key": "a/b.txt"},
            read_only=True,
            confidence=1.0,
        ),
        read_only=True,
        max_rows=10,
    )
    assert exists["data"]["exists"] is True
