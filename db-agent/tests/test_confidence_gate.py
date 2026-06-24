import pytest

from app.intent_policy import check_confidence
from app.intent_schema import IntentDocument


def test_confidence_blocks_agent_caller():
    intent = IntentDocument(
        backend="qdrant",
        operation="list_collections",
        params={},
        confidence=0.5,
        rationale="low",
    )
    err = check_confidence(intent, agent_caller="cursor", parse_source="llm")
    assert err is not None


def test_structured_skips_confidence_gate():
    intent = IntentDocument(
        backend="qdrant",
        operation="list_collections",
        params={},
        confidence=0.1,
        rationale="structured",
    )
    err = check_confidence(intent, agent_caller="cursor", parse_source="structured")
    assert err is None
