import pytest
from pathlib import Path
from tools.temporal.plugin import get_tool


def test_temporal_plugin_parse_rules():
    tool = get_tool()
    intent = tool.parse_rules("list running temporal workflows", backend_hint="temporal")
    assert intent is not None
    assert intent.backend == "temporal"
    assert intent.operation == "list_workflows"
    assert intent.params.get("status") == "Running"


def test_temporal_plugin_describe_parse():
    tool = get_tool()
    intent = tool.parse_rules("describe temporal workflow alert-incident-1", backend_hint="temporal")
    assert intent is not None
    assert intent.operation == "describe_workflow"
