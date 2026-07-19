from tools._protocol import IntegrationTool
from tools.document.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == 'document'
    assert set(tool.operations()) == {'put', 'get', 'exists', 'signed-url.create'}
