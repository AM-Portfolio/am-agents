"""Map functional + design review state to final test status."""
from __future__ import annotations

from typing import Any

from app.config import settings


def compute_final_status(state: dict[str, Any]) -> str:
    failures = state.get("failures_encountered") or []
    if failures:
        return "FAILED"

    summary = state.get("design_review_summary") or {}
    if summary.get("skipped"):
        return "PASSED"

    verdict = summary.get("overall_verdict", "pass")
    if verdict == "fail":
        return "FAILED"
    if verdict == "drift":
        return "PASSED_WITH_DESIGN_DRIFT"
    return "PASSED"


def is_functionally_passing(status: str) -> bool:
    return status in ("PASSED", "PASSED_WITH_DESIGN_DRIFT")


def should_fail_run(status: str) -> bool:
    if status == "FAILED":
        return True
    if status == "PASSED_WITH_DESIGN_DRIFT" and settings.DESIGN_GATE_STRICT:
        return True
    return False
