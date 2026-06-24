from tools.mongodb.search.parse_rules import parse_rules


def test_parse_rules_email_find():
    intent = parse_rules(
        "find mongo user with email alice@example.com",
        tool_name="mongodb",
        backend_hint="mongodb",
    )
    assert intent is not None
    assert intent.backend == "mongodb"
    assert intent.operation == "find"
    assert intent.params["entity"] == "user"
    assert intent.params["lookup_field"] == "email"
    assert intent.params["lookup_value"] == "alice@example.com"


def test_parse_rules_list_databases():
    intent = parse_rules(
        "list mongo databases",
        tool_name="mongodb",
        backend_hint="mongodb",
    )
    assert intent is not None
    assert intent.backend == "mongodb"
    assert intent.operation == "list_databases"
    assert intent.params == {}
