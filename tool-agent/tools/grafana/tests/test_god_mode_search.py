from tools._shared.god_mode import strip_god_mode
from tools.grafana.search.logql_builders import extract_trace_id, extract_portfolio_id
from tools.grafana.search.parse_rules import parse_rules


def test_strip_god_mode_prefix():
    query, enabled = strip_god_mode("god mode: find error logs in am-apps-preprod")
    assert enabled is True
    assert query == "find error logs in am-apps-preprod"


def test_parse_rules_trace_id():
    trace = "04838db7-17f3-4cff-8bf0-4d878b3b8878"
    intent = parse_rules(
        f"find logs for trace id {trace} in am-apps-preprod last 2 hours",
        tool_name="grafana",
        backend_hint="grafana",
    )
    assert intent is not None
    assert intent.operation == "query_logs"
    assert trace in intent.params["query"]
    assert intent.params["start"] == "now-2h"


def test_parse_rules_portfolio_in_logs():
    pid = "163d0143-4fcb-480c-ac20-622f14e0e293"
    intent = parse_rules(
        f"search logs for portfolio id {pid} last 24 hours",
        tool_name="grafana",
        backend_hint="grafana",
    )
    assert intent is not None
    assert intent.operation == "query_logs"
    assert pid in intent.params["query"]


def test_parse_rules_debug_500():
    intent = parse_rules(
        "investigate 500 errors for am-parser in am-apps-preprod last 1 hour",
        tool_name="grafana",
        backend_hint="grafana",
    )
    assert intent is not None
    assert intent.operation == "query_logs"
    assert "500" in intent.params["query"]
    assert "am-parser" in intent.params["query"]


def test_parse_rules_error_logs_uses_query_logs_not_sift():
    intent = parse_rules(
        "find error logs in am-apps-preprod last 1 hour",
        tool_name="grafana",
        backend_hint="grafana",
    )
    assert intent is not None
    assert intent.operation == "query_logs"
    assert intent.params["start"] == "now-1h"
    assert 'namespace="am-apps-preprod"' in intent.params["query"]


def test_extract_trace_id_labeled():
    assert extract_trace_id("traceId: 04838db7-17f3-4cff-8bf0-4d878b3b8878") == "04838db7-17f3-4cff-8bf0-4d878b3b8878"


def test_extract_portfolio_id_labeled():
    assert (
        extract_portfolio_id("portfolio id 163d0143-4fcb-480c-ac20-622f14e0e293")
        == "163d0143-4fcb-480c-ac20-622f14e0e293"
    )
