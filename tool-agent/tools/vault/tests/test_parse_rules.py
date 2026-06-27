from tools.vault.search.fuzzy import fuzzy_entity_from_query, resolve_vault_target, target_to_params
from tools.vault.search.parse_rules import parse_rules


def test_parse_rules_read_preprod_service_reads_default_entity():
    intent = parse_rules(
        "read secret preprod service",
        tool_name="vault",
        backend_hint="vault",
    )
    assert intent is not None
    assert intent.operation == "read_secret"
    assert intent.params.get("entity") or "preprod/services" in intent.params.get("path", "")


def test_parse_rules_read_preprod_infra_reads_default_entity():
    intent = parse_rules(
        "read secret preprod infra",
        tool_name="vault",
        backend_hint="vault",
    )
    assert intent is not None
    assert intent.operation == "read_secret"
    assert intent.params.get("entity") or "preprod/infra" in intent.params.get("path", "")


def test_fuzzy_entity_identity():
    assert fuzzy_entity_from_query("read secret preprod identity") == "am_identity"


def test_fuzzy_entity_postgres_typo():
    assert fuzzy_entity_from_query("read secret preprod postgress") == "postgres_infra"


def test_resolve_target_service_category():
    target = resolve_vault_target("read secret preprod service")
    assert target.category == "services"
    assert target.operation == "read_secret"
    assert target.entity or target.path


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


def test_parse_rules_read_postgres_typo():
    intent = parse_rules(
        "read secret preprod postgress",
        tool_name="vault",
        backend_hint="vault",
    )
    assert intent is not None
    assert intent.operation == "read_secret"
    assert intent.params.get("entity") == "postgres_infra" or "postgres" in str(intent.params.get("path", ""))


def test_parse_rules_read_postgres_entity():
    intent = parse_rules(
        "read vault postgres secret in preprod",
        tool_name="vault",
        backend_hint="vault",
    )
    assert intent is not None
    assert intent.operation == "read_secret"
    assert intent.params.get("entity") == "postgres_infra"


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
