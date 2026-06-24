from tools._protocol import IntegrationTool
from tools.qdrant.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == "qdrant"
    assert set(tool.operations()) == {
        "list_collections",
        "collection_info",
        "scroll",
        "search",
    }
