from tools._protocol import IntegrationTool
from tools.alert.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == "alert"
    assert set(tool.operations()) == {"silence.create", "silence.get", "silence.expire"}
