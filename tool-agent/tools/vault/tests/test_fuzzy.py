from tools.vault.search.fuzzy import resolve_vault_target, target_to_params


def test_read_gateway_fuzzy():
    target = resolve_vault_target("read secret preprod mcp gateway")
    assert target.entity == "am_mcp_gateway"
    assert target.operation == "read_secret"
    params = target_to_params(target)
    assert "am-mcp-gateway" in params.get("path", "")


def test_read_leaf_under_services():
    target = resolve_vault_target("read secret preprod services am-identity")
    assert target.operation == "read_secret"
    assert "am-identity" in (target.path or "")
