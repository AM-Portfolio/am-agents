from tools.vault.search.parse_rules import parse_rules


def test_parse_rules_list_infra():
    intent = parse_rules(
        "list vault secrets under apps/data/preprod/infra",
        tool_name="vault",
        backend_hint="vault",
    )
    assert intent is not None
    assert intent.backend == "vault"
    assert intent.operation == "list_secrets"
    assert "preprod" in intent.params["path"]


def test_parse_rules_read_postgres_entity():
    intent = parse_rules(
        "read vault postgres secret in preprod",
        tool_name="vault",
        backend_hint="vault",
    )
    assert intent is not None
    assert intent.operation == "read_secret"
    assert intent.params["entity"] == "postgres_infra"


def test_parse_rules_list_mounts():
    intent = parse_rules("list vault mounts", tool_name="vault", backend_hint="vault")
    assert intent is not None
    assert intent.operation == "list_mounts"


def test_parse_rules_write_blocked_on_query_path():
    intent = parse_rules(
        "write vault secret postgres key foo value bar",
        tool_name="vault",
        backend_hint="vault",
    )
    assert intent is not None
    assert intent.operation == "write_secret"
    assert intent.read_only is False
