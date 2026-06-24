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
