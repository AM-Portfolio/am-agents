import pytest

from app.models.intent import IntentDocument
from tools.work_item.plugin import get_tool


@pytest.mark.asyncio
async def test_memory_execute_roundtrip(monkeypatch):
    monkeypatch.setenv("WORK_ITEM_PROVIDER", "memory")
    monkeypatch.setenv("TOOL_AGENT_ALLOW_WRITES", "true")
    tool = get_tool()
    create = IntentDocument(
        backend=tool.name,
        operation="create",
        params={"title": "t1", "idempotency_key": "wi-1"},
        read_only=False,
        confidence=1.0,
    )
    created = await tool.execute(create, read_only=False, max_rows=10)
    assert created["ok"] is True
    ref = created["data"]["work_item_ref"]
    got = await tool.execute(
        IntentDocument(
            backend=tool.name,
            operation="get",
            params={"work_item_ref": ref},
            read_only=True,
            confidence=1.0,
        ),
        read_only=True,
        max_rows=10,
    )
    assert got["data"]["work_item_ref"] == ref
