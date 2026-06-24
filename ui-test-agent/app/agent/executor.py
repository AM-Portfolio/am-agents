from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.state import AutonomousAgentState
from app.browser.actions import run_browser_action
from app.browser.screenshot import capture_screenshot_base64
from app.context import get_test_context

logger = logging.getLogger(__name__)


async def executor_node(state: AutonomousAgentState, config: RunnableConfig) -> dict[str, Any]:
    ctx = get_test_context(config)
    page = ctx.page
    if page is None:
        raise RuntimeError("Playwright page not initialized")

    idx = state.get("current_step_index", 0)
    steps = state.get("steps") or []
    if idx >= len(steps):
        return {}

    step = steps[idx]
    step_name = step.get("name", str(step))
    step_action = step.get("action", "")
    logger.info("Executing step %d/%d: %s", idx + 1, len(steps), step_name)

    screenshot_history = list(state.get("screenshot_history") or [])
    screenshot_labels = list(state.get("screenshot_labels") or [])

    t0 = time.perf_counter()
    try:
        await run_browser_action(page, step, ctx)
        duration_ms = (time.perf_counter() - t0) * 1000
        if ctx.action_log:
            ctx.action_log[-1]["duration_ms"] = round(duration_ms, 1)
        ctx.record_step_timing(
            index=idx,
            name=step_name,
            action=step_action,
            phase="execute",
            duration_ms=duration_ms,
            status="ok",
        )
        if step.get("action") in (
            "screenshot",
            "navigate",
            "click",
            "fill",
            "fill_label",
            "click_button",
            "click_demo_login",
            "wait_for_flutter",
            "wait_for_login",
        ):
            shot = await capture_screenshot_base64(page)
            screenshot_history.append(shot)
            screenshot_labels.append(step_name)
    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.error("Step failed: %s", exc)
        ctx.record_step_timing(
            index=idx,
            name=step_name,
            action=step_action,
            phase="execute",
            duration_ms=duration_ms,
            status="failed",
            error=str(exc),
        )
        failures = list(state.get("failures_encountered") or [])
        failure_type = "selector_not_found" if "timeout" in str(exc).lower() else "step_error"
        failures.append(
            {
                "type": failure_type,
                "step_index": idx,
                "step": step,
                "error": str(exc),
            }
        )
        ctx.log_action("step_failed", step=step_name, error=str(exc), duration_ms=duration_ms)
        return {
            "current_step_index": idx + 1,
            "failures_encountered": failures,
            "screenshot_history": screenshot_history,
            "screenshot_labels": screenshot_labels,
        }

    return {
        "current_step_index": idx + 1,
        "screenshot_history": screenshot_history,
        "screenshot_labels": screenshot_labels,
    }
