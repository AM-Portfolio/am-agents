from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.state import AutonomousAgentState
from app.context import get_test_context

logger = logging.getLogger(__name__)


def _fail(state, idx, step, error: str, ctx, duration_ms: float) -> dict:
    failures = list(state.get("failures_encountered") or [])
    failures.append(
        {
            "type": "assertion_failed",
            "step_index": idx,
            "step": step,
            "error": error,
        }
    )
    ctx.record_step_timing(
        index=idx,
        name=step.get("name", step.get("action", "")),
        action=step.get("action", ""),
        phase="assert",
        duration_ms=duration_ms,
        status="failed",
        error=error,
    )
    ctx.log_action("assert_failed", step=step.get("name"), error=error, duration_ms=duration_ms)
    return {"failures_encountered": failures}


async def assert_node(state: AutonomousAgentState, config: RunnableConfig) -> dict[str, Any]:
    ctx = get_test_context(config)
    page = ctx.page
    if page is None:
        raise RuntimeError("Playwright page not initialized")

    idx = max(0, state.get("current_step_index", 1) - 1)
    steps = state.get("steps") or []
    if idx >= len(steps):
        return {}

    step = steps[idx]
    action = step.get("action")
    name = step.get("name", action)
    t0 = time.perf_counter()

    if action == "assert_title_not_empty":
        title = await page.title()
        duration_ms = (time.perf_counter() - t0) * 1000
        if not title or not title.strip():
            return _fail(state, idx, step, "Page title is empty", ctx, duration_ms)
        ctx.record_step_timing(
            index=idx, name=name, action=action, phase="assert", duration_ms=duration_ms, status="ok"
        )
        ctx.log_action("assert_pass", step=name, title=title, duration_ms=duration_ms)
        logger.info("[%s] PASS title=%r", name, title)

    elif action == "assert_url_contains":
        pattern = step["pattern"]
        current = page.url
        duration_ms = (time.perf_counter() - t0) * 1000
        if pattern not in current:
            return _fail(
                state, idx, step, f"URL {current!r} does not contain {pattern!r}", ctx, duration_ms
            )
        ctx.record_step_timing(
            index=idx, name=name, action=action, phase="assert", duration_ms=duration_ms, status="ok"
        )
        ctx.log_action("assert_pass", step=name, url=current, duration_ms=duration_ms)
        logger.info("[%s] PASS url=%s", name, current)

    elif action == "assert_text_visible":
        texts = step.get("texts") or [step.get("text", "")]
        timeout = int(step.get("timeout_ms", 20000))
        for text in texts:
            if not text:
                continue
            try:
                await page.get_by_text(text, exact=False).first.wait_for(
                    state="visible", timeout=timeout
                )
            except Exception as exc:
                duration_ms = (time.perf_counter() - t0) * 1000
                return _fail(state, idx, step, f"Text not visible: {text!r} ({exc})", ctx, duration_ms)
        duration_ms = (time.perf_counter() - t0) * 1000
        ctx.record_step_timing(
            index=idx, name=name, action=action, phase="assert", duration_ms=duration_ms, status="ok"
        )
        ctx.log_action("assert_pass", step=name, texts=texts, duration_ms=duration_ms)
        logger.info("[%s] PASS texts=%s", name, texts)

    return {}
