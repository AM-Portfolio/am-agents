"""Tests for report metrics and document building."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.agent.report_metrics import (
    build_release_gate,
    build_report_document,
    render_report_html,
    write_baseline_bundle,
)
from app.context import TestRunContext


def _ctx() -> TestRunContext:
    ctx = TestRunContext(
        test_id="abc-123",
        session_id="ui-test-abc",
        profile="AUTH_FLOW_MAIN",
        llm_client=MagicMock(),
        branch="main",
    )
    ctx.mark_run_start()
    ctx.record_step_timing(
        index=0,
        name="Open app",
        action="navigate",
        phase="execute",
        duration_ms=1200.5,
        status="ok",
    )
    ctx.log_action("navigate", step="Open app", url="https://example.com", duration_ms=1200.5)
    ctx.log_action("assert_pass", step="Assert home", url="https://example.com/#/home", duration_ms=45.2)
    return ctx


def test_build_report_document_contains_timing_and_results():
    ctx = _ctx()
    state = {
        "target_url": "https://example.com",
        "steps": [{"action": "navigate", "name": "Open app", "url": "https://example.com"}],
        "failures_encountered": [],
        "screenshot_history": [],
        "screenshot_labels": [],
    }
    doc = build_report_document(ctx=ctx, state=state, status="PASSED", report_path="/tmp/x.html")
    assert doc["schema"] == "am-ui-test-report/v2"
    assert doc["status"] == "PASSED"
    assert doc["timing"]["step_count"] == 1
    assert doc["timing"]["assert_pass_count"] == 1
    assert doc["results"]["passed"] is True
    assert "environment" in doc
    assert "llm_routing" in doc["environment"]
    assert "release_gate" in doc
    assert doc["release_gate"]["decision"] in ("GO", "GO_WITH_CAVEATS", "BASELINE_SEEDED", "NO_GO")


def test_render_report_html_includes_metrics_sections():
    ctx = _ctx()
    state = {
        "target_url": "https://example.com",
        "steps": [],
        "failures_encountered": [],
        "screenshot_history": [],
        "screenshot_labels": [],
    }
    doc = build_report_document(ctx=ctx, state=state, status="PASSED", report_path="/tmp/x.html")
    html = render_report_html(doc, screenshots_html="<p>none</p>")
    assert "Step timeline (latency)" in html
    assert "Total time" in html
    assert "Environment" in html
    assert "Execution log" in html
    assert "Release gate" in html or "release-gate" in html
    assert "PASSED" in html


def test_release_gate_seed_mode():
    gate = build_release_gate(
        status="PASSED",
        results={"checklist_fail": 0, "checklist_pass": 5, "checklist_total": 5},
        design={
            "baseline_mode": "seed",
            "skipped": False,
            "auto_reviewed": True,
            "review_required": False,
            "overall_verdict": "pass",
            "screenshots": [{"verdict": "seeded", "llm_called": False}],
        },
        timing={"step_fail_count": 0, "assert_fail_count": 0, "step_count": 3},
        failures=[],
    )
    assert gate["decision"] == "BASELINE_SEEDED"
    assert any(g["id"] == "baseline_compare" for g in gate["gates"])
