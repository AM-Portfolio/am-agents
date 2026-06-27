from tools.vault.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert tool.name == "vault"
    assert "read_secret" in tool.operations()
    assert "write_secret" in tool.operations()
