"""Tests for design status computation."""
from __future__ import annotations

from app.agent.design_status import compute_final_status, should_fail_run


def test_compute_final_status_passed():
    state = {"failures_encountered": [], "design_review_summary": {"skipped": True}}
    assert compute_final_status(state) == "PASSED"


def test_compute_final_status_failed_functional():
    state = {"failures_encountered": [{"type": "assertion_failed"}], "design_review_summary": {}}
    assert compute_final_status(state) == "FAILED"


def test_compute_final_status_drift():
    state = {
        "failures_encountered": [],
        "design_review_summary": {"overall_verdict": "drift"},
    }
    assert compute_final_status(state) == "PASSED_WITH_DESIGN_DRIFT"


def test_compute_final_status_design_fail():
    state = {
        "failures_encountered": [{"type": "design_regression"}],
        "design_review_summary": {"overall_verdict": "fail"},
    }
    assert compute_final_status(state) == "FAILED"


def test_should_fail_run_balanced_allows_drift():
    assert should_fail_run("PASSED_WITH_DESIGN_DRIFT") is False
    assert should_fail_run("FAILED") is True
