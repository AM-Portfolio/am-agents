from tools._protocol import IntegrationTool
from tools.kafka.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == "kafka"
    assert set(tool.operations()) == {
        "list_topics",
        "describe_topic",
        "peek_messages",
        "consumer_lag",
    }
