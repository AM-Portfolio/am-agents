from tools._template.search.parse_rules import parse_rules


def test_parse_rules_ping():
    intent = parse_rules("ping", tool_name="example")
    assert intent is not None
    assert intent.operation == "ping"
