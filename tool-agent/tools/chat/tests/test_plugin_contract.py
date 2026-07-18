from tools._protocol import IntegrationTool
from tools.chat.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == 'chat'
    assert set(tool.operations()) == {'message.send', 'card.send'}
