import pytest

from app.models.intent import IntentDocument
from tools.spt.plugin import get_tool


@pytest.mark.asyncio
async def test_memory_execute_roundtrip(monkeypatch):
    monkeypatch.setenv("SPT_PROVIDER", "memory")
    monkeypatch.setenv("TOOL_AGENT_ALLOW_WRITES", "true")
    tool = get_tool()
    prep = await tool.execute(
        IntentDocument(
            backend=tool.name,
            operation="test-data.prepare",
            params={"demand_ref": "d1", "idempotency_key": "spt-1"},
            read_only=False,
            confidence=1.0,
        ),
        read_only=False,
        max_rows=10,
    )
    assert prep["ok"] is True
    run = await tool.execute(
        IntentDocument(
            backend=tool.name,
            operation="execute",
            params={"demand_ref": "d1", "sandbox": True, "idempotency_key": "spt-2"},
            read_only=False,
            confidence=1.0,
        ),
        read_only=False,
        max_rows=10,
    )
    assert run["status"] == "accepted"
    assert run["async_operation_ref"]
