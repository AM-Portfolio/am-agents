from tools.kafka.search.convention import extract_topic, normalize_topic
from tools.vault.search.convention import resolve_convention


def test_normalize_topic_alias():
    assert normalize_topic("am-portfolio-events") == "am-portfolio-update"


def test_extract_portfolio_stream():
    assert extract_topic("peek last message on am-portfolio-stream topic") == "am-portfolio-stream"


def test_vault_infra_postgres_typo():
    result = resolve_convention("read secret preprod postgress")
    assert result.path == "preprod/infra/postgres"
    assert result.entity == "postgres_infra"


def test_vault_service_am_identity():
    result = resolve_convention("read secret preprod services am-identity")
    assert result.path == "preprod/services/am-identity"


def test_vault_mcp_gateway_hint():
    result = resolve_convention("read secret preprod mcp gateway")
    assert result.path == "preprod/services/am-mcp-gateway"
