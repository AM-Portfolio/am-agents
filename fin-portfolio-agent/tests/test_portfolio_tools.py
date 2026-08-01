"""
Tests for tools/portfolio_tools.py — _format() helper.

The function has two branches:
  1. "error" key in data → human-readable error string (not JSON).
  2. Normal data → pure JSON string.

Covers:
- Normal dict → json.loads round-trips successfully
- Empty dict → valid JSON "{}"
- Label string NOT present in JSON output
- Error dict → human-readable string, json.loads raises
- Return type is always str
- Nested dict round-trips correctly
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# _format is a module-level private helper; import it directly.
# We patch the external dependency (analysis_client) at import time by
# providing a stub so the module loads without a live service.
import unittest.mock as mock

# Stub out analysis_client before importing portfolio_tools so the module
# import does not fail due to missing network/config dependencies.
_fake_client = mock.MagicMock()
with mock.patch.dict("sys.modules", {
    "am_fin_portfolio_analysis.clients.analysis_client": mock.MagicMock(analysis_client=_fake_client),
    "shared.tools.registry": mock.MagicMock(register_tool=lambda **kw: (lambda f: f)),
    "shared.context.request_context": mock.MagicMock(user_id_var=mock.MagicMock()),
}):
    import importlib
    import am_fin_portfolio_analysis.tools.portfolio_tools as _pt_module

# Re-import with patches active so _format is accessible.
# Because the module may already be cached, just grab _format from it.
_format = _pt_module._format


# ─── tests ───────────────────────────────────────────────────────────────────

class TestFormatNormalData:
    def test_normal_dict_is_valid_json(self):
        result = _format({"totalValue": 1_000_000}, "Portfolio Summary")
        parsed = json.loads(result)
        assert parsed["totalValue"] == 1_000_000

    def test_return_type_is_str(self):
        result = _format({"x": 1}, "Any Label")
        assert isinstance(result, str)

    def test_empty_dict_produces_valid_json(self):
        result = _format({}, "Empty")
        assert json.loads(result) == {}

    def test_label_not_present_in_json_output(self):
        label = "PortfolioSummaryLabel"
        result = _format({"k": "v"}, label)
        assert label not in result

    def test_values_round_trip(self):
        data = {
            "totalValue": 500,
            "gainLoss": -20.5,
            "name": "Test Portfolio",
            "active": True,
        }
        result = _format(data, "test")
        assert json.loads(result) == data

    def test_nested_dict_round_trips(self):
        data = {
            "summary": {
                "best": {"symbol": "RELIANCE", "changePercent": 3.5},
                "worst": {"symbol": "INFY", "changePercent": -1.2},
            },
            "count": 15,
        }
        result = _format(data, "Nested")
        assert json.loads(result) == data

    def test_list_value_round_trips(self):
        data = {"holdings": [{"symbol": "TCS"}, {"symbol": "HDFC"}]}
        result = _format(data, "Holdings")
        assert json.loads(result)["holdings"][1]["symbol"] == "HDFC"


class TestFormatErrorData:
    def test_error_dict_returns_human_readable_string(self):
        result = _format({"error": "Service unavailable"}, "Portfolio Summary")
        assert "Service unavailable" in result

    def test_error_dict_result_is_not_valid_json(self):
        result = _format({"error": "Connection refused"}, "Portfolio Summary")
        # The error branch returns a plain English string, not JSON.
        try:
            json.loads(result)
            assert False, "Expected json.loads to raise for error output"
        except (ValueError, json.JSONDecodeError):
            pass  # expected

    def test_error_dict_mentions_label(self):
        result = _format({"error": "timeout"}, "Portfolio Summary")
        assert "Portfolio Summary" in result

    def test_error_dict_return_type_is_str(self):
        result = _format({"error": "oops"}, "Test")
        assert isinstance(result, str)

    def test_error_string_contains_port_hint(self):
        """The error message should mention am-analysis port 8060."""
        result = _format({"error": "down"}, "Any")
        assert "8060" in result

    def test_non_error_dict_with_other_keys_is_valid_json(self):
        """Only the 'error' key triggers the error branch — other keys produce JSON."""
        data = {"status": "ok", "message": "all good"}
        result = _format(data, "status check")
        assert json.loads(result) == data
