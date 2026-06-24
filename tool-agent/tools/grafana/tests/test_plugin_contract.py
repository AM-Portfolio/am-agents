from tools._protocol import IntegrationTool
from tools.grafana.plugin import get_tool


def test_plugin_contract():
    tool = get_tool()
    assert isinstance(tool, IntegrationTool)
    assert tool.name == "grafana"
    assert set(tool.operations()) == {
        "query_logs",
        "list_labels",
        "list_label_values",
        "query_patterns",
        "find_error_logs",
        "query_metrics",
        "search_dashboards",
        "get_dashboard",
        "list_datasources",
    }
