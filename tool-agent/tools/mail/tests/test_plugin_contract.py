from tools._protocol import IntegrationTool
from tools.mail.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == 'mail'
    assert set(tool.operations()) == {'message.send'}
