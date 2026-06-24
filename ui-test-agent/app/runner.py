"""Run the full UI test graph locally (Playwright → Qdrant design review → LiteLLM → report)."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from app.agent.graph import test_agent_graph
from app.browser.controller import browser_controller
from app.config import settings
from app.context import TestRunContext
from app.llm.factory import create_llm_client

logger = logging.getLogger(__name__)


async def execute_ui_test(test_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Execute plan → execute → assert → design_review → report.

    Returns result dict with keys: status, report, error, design_review, sessionId, ...
    """
    session_id = f"ui-test-{test_id[:8]}"
    llm_client = create_llm_client()
    baseline_mode = (payload.get("baselineMode") or settings.BASELINE_MODE).lower()

    ctx = TestRunContext(
        test_id=test_id,
        session_id=session_id,
        profile=payload["profile"],
        llm_client=llm_client,
        commit_sha=payload.get("commitSha"),
        branch=payload.get("branch", "main"),
        baseline_mode=baseline_mode,
    )
    ctx.mark_run_start()

    out: dict[str, Any] = {
        "testId": test_id,
        "status": "RUNNING",
        "sessionId": session_id,
        "baseline_mode": baseline_mode,
    }

    try:
        await browser_controller.start(headless=settings.HEADLESS)
        async with browser_controller.get_page(
            viewport_width=settings.BROWSER_VIEWPORT_WIDTH,
            viewport_height=settings.BROWSER_VIEWPORT_HEIGHT,
        ) as page:
            ctx.page = page
            initial_state: dict[str, Any] = {
                "target_url": payload["targetUrl"],
                "specification": payload.get("specification") or "",
                "steps": [],
                "current_step_index": 0,
                "selectors_db": {},
                "failures_encountered": [],
                "screenshot_history": [],
                "screenshot_labels": [],
                "report_output": None,
                "mongodb_report_id": None,
                "testing_goal": f"Execute {payload['profile']} for branch {payload.get('branch')}",
                "git_diff": None,
                "visited_routes": [],
                "action_log": [],
                "visual_anomalies": [],
                "design_review_results": [],
                "design_review_summary": {},
                "baseline_mode": baseline_mode,
            }
            result = await test_agent_graph.ainvoke(
                initial_state,
                config={"configurable": {"test_context": ctx}},
            )

        out["status"] = "COMPLETED"
        out["report"] = result.get("report_output")
        out["action_log"] = ctx.action_log
        out["duration_ms"] = ctx.total_duration_ms()
        out["step_timings"] = ctx.step_timings
        out["design_review"] = result.get("design_review_summary")
        logger.info("UI test %s completed — report %s", test_id, result.get("report_output"))
        return out
    except Exception as exc:
        logger.error("UI test %s failed: %s", test_id, exc)
        out["status"] = "FAILED"
        out["error"] = str(exc)
        out["action_log"] = ctx.action_log
        out["duration_ms"] = ctx.total_duration_ms()
        out["step_timings"] = ctx.step_timings
        from pathlib import Path

        report_guess = Path(settings.REPORT_DIR) / f"{test_id}.html"
        if report_guess.is_file():
            out["report"] = str(report_guess)
        return out
    finally:
        await browser_controller.stop()
