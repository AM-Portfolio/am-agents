from tools._protocol import IntegrationTool
from tools.mongodb.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == "mongodb"
    assert "find" in tool.operations()
    assert "list_databases" in tool.operations()
