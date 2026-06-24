from tools._protocol import IntegrationTool
from tools.postgres.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == "postgres"
    assert "run_sql" in tool.operations()
    assert "search_schema" in tool.operations()
