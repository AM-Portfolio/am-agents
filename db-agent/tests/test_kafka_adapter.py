from __future__ import annotations

from unittest.mock import patch

import pytest

from adapters.kafka import KafkaAdapter


@pytest.mark.asyncio
async def test_kafka_list_topics():
    with patch("adapters.kafka._list_topics_sync") as mock_list:
        mock_list.return_value = {"topics": [{"name": "orders", "partitions": 2}], "count": 1}
        adapter = KafkaAdapter()
        result = await adapter.execute("list_topics", {}, read_only=True, max_rows=100)

    assert result["count"] == 1
    assert result["topics"][0]["name"] == "orders"


@pytest.mark.asyncio
async def test_kafka_peek_messages_from_tail():
    with patch("adapters.kafka._peek_messages_sync") as mock_peek:
        mock_peek.return_value = {
            "topic": "am-stock-price-update",
            "messages": [{"offset": 99, "value": '{"price": 1}'}],
            "count": 1,
        }
        adapter = KafkaAdapter()
        result = await adapter.execute(
            "peek_messages",
            {"topic": "am-stock-price-update", "limit": 1, "from_tail": True},
            read_only=True,
            max_rows=100,
        )

    mock_peek.assert_called_once_with("am-stock-price-update", limit=1, from_tail=True)
    assert result["count"] == 1
    assert result["peek_source"] == "native"


@pytest.mark.asyncio
async def test_kafka_peek_falls_back_to_kafka_ui_on_resolve_error():
    with patch("adapters.kafka._peek_messages_sync", side_effect=Exception("Host resolution failure")):
        with patch("adapters.kafka._peek_messages_via_ui_sync") as mock_ui:
            mock_ui.return_value = {
                "topic": "am-stock-price-update",
                "messages": [{"offset": 424779, "value": '{"eventType":"EQUITY_PRICE_UPDATE"}'}],
                "count": 1,
                "peek_source": "kafka-ui",
            }
            with patch("adapters.kafka._kafka_ui_configured", return_value=True):
                with patch("adapters.kafka.settings.KAFKA_PEEK_MODE", "auto"):
                    adapter = KafkaAdapter()
                    result = await adapter.execute(
                        "peek_messages",
                        {"topic": "am-stock-price-update", "limit": 1, "from_tail": True},
                        read_only=True,
                        max_rows=100,
                    )

    mock_ui.assert_called_once_with("am-stock-price-update", limit=1, from_tail=True)
    assert result["peek_source"] == "kafka-ui"


@pytest.mark.asyncio
async def test_kafka_describe_topic_requires_name():
    adapter = KafkaAdapter()
    with pytest.raises(ValueError, match="topic required"):
        await adapter.execute("describe_topic", {}, read_only=True, max_rows=10)
