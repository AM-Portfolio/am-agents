from tools._protocol import IntegrationTool
from tools.redis.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == "redis"
    assert set(tool.operations()) == {"scan_keys", "get", "info", "type"}
