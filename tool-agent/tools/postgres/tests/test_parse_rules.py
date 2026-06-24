from tools.postgres.search.parse_rules import parse_rules


def test_parse_rules_email_find():
    intent = parse_rules(
        "find postgres user with email alice@example.com",
        tool_name="postgres",
        backend_hint="postgres",
    )
    assert intent is not None
    assert intent.backend == "postgres"
    assert intent.operation == "run_sql"
    assert intent.params["entity"] == "user_account"
    assert intent.params["lookup_field"] == "email"
    assert intent.params["lookup_value"] == "alice@example.com"


def test_parse_rules_search_schema():
    intent = parse_rules(
        "postgres search schema for portfolio tables",
        tool_name="postgres",
        backend_hint="postgres",
    )
    assert intent is not None
    assert intent.backend == "postgres"
    assert intent.operation == "search_schema"
    assert intent.params["pattern"] == "portfolio"
