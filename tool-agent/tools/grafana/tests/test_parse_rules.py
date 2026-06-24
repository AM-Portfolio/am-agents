from tools.grafana.search.parse_rules import parse_rules


def test_parse_rules_query_logs_namespace_pod():
    intent = parse_rules(
        "loki logs for am-tool-agent in am-apps-preprod namespace last 30 minutes",
        tool_name="grafana",
        backend_hint="grafana",
    )
    assert intent is not None
    assert intent.backend == "grafana"
    assert intent.operation == "query_logs"
    assert "am-apps-preprod" in intent.params["query"]
    assert intent.params["start"] == "now-30m"


def test_parse_rules_list_datasources():
    intent = parse_rules(
        "list grafana datasources",
        tool_name="grafana",
        backend_hint="grafana",
    )
    assert intent is not None
    assert intent.operation == "list_datasources"


def test_parse_rules_search_dashboards():
    intent = parse_rules(
        "search grafana dashboards for kafka",
        tool_name="grafana",
        backend_hint="grafana",
    )
    assert intent is not None
    assert intent.operation == "search_dashboards"
    assert intent.params["query"] == "kafka"
