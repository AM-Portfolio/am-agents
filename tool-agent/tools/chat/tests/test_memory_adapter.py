import pytest

from app.models.intent import IntentDocument
from tools.chat.plugin import get_tool


@pytest.mark.asyncio
async def test_memory_execute_roundtrip(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "memory")
    monkeypatch.setenv("TOOL_AGENT_ALLOW_WRITES", "true")
    tool = get_tool()
    result = await tool.execute(
        IntentDocument(
            backend=tool.name,
            operation="message.send",
            params={"channel_ref": "cliq:lab", "body": "hello", "idempotency_key": "c1"},
            read_only=False,
            confidence=1.0,
        ),
        read_only=False,
        max_rows=10,
    )
    assert result["ok"] is True
    assert result["provider"] == "memory"
