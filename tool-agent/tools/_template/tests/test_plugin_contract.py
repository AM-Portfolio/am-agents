from tools._protocol import IntegrationTool
from tools._template.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == "_template"
