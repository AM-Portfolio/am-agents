import pytest

from app.config import settings
from app.models.intent import IntentDocument
from app.nodes.parse_intent import parse_intent_node
from app.models.intent import ToolsQueryRequest
from app.state import ToolAgentState


@pytest.mark.asyncio
async def test_low_confidence_rules_fall_through_without_llm(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "TOOL_AGENT_INTENT_MIN_CONFIDENCE", 0.75)
    monkeypatch.setattr(settings, "LLM_INTENT_ENABLED", False)

    state: ToolAgentState = {
        "request_id": "test",
        "request": ToolsQueryRequest(
            query="peek last kafka message",
            backend="kafka",
            read_only=True,
        ),
        "max_rows": 100,
    }
    result = await parse_intent_node(state)
    assert result.get("error")
    assert result.get("error_status") == 422


@pytest.mark.asyncio
async def test_high_confidence_rules_used(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "TOOL_AGENT_INTENT_MIN_CONFIDENCE", 0.75)
    monkeypatch.setattr(settings, "LLM_INTENT_ENABLED", False)

    state: ToolAgentState = {
        "request_id": "test",
        "request": ToolsQueryRequest(
            query="list kafka topics",
            backend="kafka",
            read_only=True,
        ),
        "max_rows": 100,
    }
    result = await parse_intent_node(state)
    assert result.get("intent") is not None
    assert result["intent"].operation == "list_topics"
    assert result.get("parse_source") == "rules"
