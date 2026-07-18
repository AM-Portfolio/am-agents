from tools._protocol import IntegrationTool
from tools.work_item.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == 'work-item'
    assert set(tool.operations()) == {'search', 'get', 'create', 'comment', 'assign', 'transition'}
