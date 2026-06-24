from __future__ import annotations

from app.nodes.parse_intent import _extract_kafka_topic, _kafka_rule_intent, _rule_based_intent


def test_extract_kafka_topic_from_am_prefix():
    query = "last message published on kafka topics am-stock-price-update"
    assert _extract_kafka_topic(query) == "am-stock-price-update"


def test_kafka_rule_intent_peek_last_message():
    query = "last message published on kafka topics am-stock-price-update"
    intent = _kafka_rule_intent(query, "kafka")
    assert intent is not None
    assert intent.backend == "kafka"
    assert intent.operation == "peek_messages"
    assert intent.params == {
        "topic": "am-stock-price-update",
        "limit": 1,
        "from_tail": True,
    }


def test_rule_based_intent_kafka_backend_hint():
    query = "last message published on kafka topics am-stock-price-update"
    intent = _rule_based_intent(query, "kafka")
    assert intent is not None
    assert intent.operation == "peek_messages"
    assert intent.params["topic"] == "am-stock-price-update"
