"""Tests for design review report integration."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.agent.report_metrics import build_report_document, render_report_html
from app.context import TestRunContext


def test_report_includes_design_review_block():
    ctx = TestRunContext(
        test_id="t-1",
        session_id="ui-test-t",
        profile="AUTH_FLOW_MAIN",
        llm_client=MagicMock(),
        baseline_mode="compare",
    )
    ctx.mark_run_start()
    state = {
        "target_url": "https://example.com",
        "steps": [],
        "failures_encountered": [],
        "screenshot_history": [],
        "screenshot_labels": [],
        "design_review_summary": {
            "enabled": True,
            "skipped": False,
            "auto_reviewed": True,
            "review_required": False,
            "overall_verdict": "pass",
            "baseline_mode": "compare",
            "screenshots": [
                {
                    "step_label": "3. Screenshot — login form visible",
                    "route": "/",
                    "similarity": 0.95,
                    "verdict": "matches_baseline",
                    "llm_called": False,
                    "llm_summary": "Auto-pass",
                }
            ],
        },
        "visual_anomalies": [],
    }
    doc = build_report_document(
        ctx=ctx, state=state, status="PASSED", report_path="/tmp/x.html"
    )
    assert "design_review" in doc
    assert doc["design_review"]["overall_verdict"] == "pass"
    assert doc["release_gate"]["decision"] == "GO"
    html = render_report_html(doc, screenshots_html="")
    assert "Design review" in html
    assert "matches_baseline" in html
    assert "release-gate" in html
