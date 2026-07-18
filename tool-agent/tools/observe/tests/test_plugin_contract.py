from tools._protocol import IntegrationTool
from tools.observe.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == 'observe'
    assert set(tool.operations()) == {'metrics.query', 'logs.query', 'timeseries.query'}
