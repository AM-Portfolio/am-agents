from tools._protocol import IntegrationTool
from tools.directory.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == 'directory'
    assert set(tool.operations()) == {'owner.resolve'}
