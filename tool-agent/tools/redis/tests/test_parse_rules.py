from tools.redis.search.parse_rules import parse_rules


def test_parse_rules_session_get():
    intent = parse_rules(
        "redis get session abcdef01-2345-6789-abcd-ef0123456789",
        tool_name="redis",
    )
    assert intent is not None
    assert intent.operation == "get"
    assert intent.params["entity"] == "session"


def test_parse_rules_scan_sessions():
    intent = parse_rules("list redis session keys", tool_name="redis")
    assert intent is not None
    assert intent.operation == "scan_keys"
    assert intent.params["pattern"] == "session:*"
