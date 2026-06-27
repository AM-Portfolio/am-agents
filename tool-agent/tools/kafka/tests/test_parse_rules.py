from tools.kafka.search.parse_rules import parse_rules


def test_parse_rules_list_topics():
    intent = parse_rules("show kafka topics", tool_name="kafka")
    assert intent is not None
    assert intent.operation == "list_topics"


def test_parse_rules_peek_messages():
    intent = parse_rules("peek last message on am-stock-price-update topic", tool_name="kafka")
    assert intent is not None
    assert intent.operation == "peek_messages"
    assert intent.params["topic"] == "am-stock-price-update"
    assert intent.params["from_tail"] is True
    assert intent.params["limit"] == 1


def test_parse_rules_peek_portfolio_stream():
    intent = parse_rules("peek last message on am-portfolio-stream topic", tool_name="kafka")
    assert intent is not None
    assert intent.operation == "peek_messages"
    assert intent.params["topic"] == "am-portfolio-stream"


def test_parse_rules_alias_wrong_portfolio_events():
    intent = parse_rules("describe kafka topic am-portfolio-events", tool_name="kafka")
    assert intent is not None
    assert intent.params["topic"] == "am-portfolio-update"


def test_parse_rules_peek_without_topic_returns_none():
    intent = parse_rules("peek last kafka message", tool_name="kafka")
    assert intent is None


def test_parse_rules_list_topics_read_only_modifier():
    """kagent-style prompt must not peek a fake 'read-only.' topic."""
    intent = parse_rules("List kafka topics read-only. backend kafka", tool_name="kafka")
    assert intent is not None
    assert intent.operation == "list_topics"
    assert intent.params == {}
