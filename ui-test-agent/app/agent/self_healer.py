from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agent.state import AutonomousAgentState
from app.browser.screenshot import capture_screenshot_base64
from app.config import settings
from app.context import get_test_context
from app.vision.analyzer import vision_analyzer

logger = logging.getLogger(__name__)


async def self_heal_node(state: AutonomousAgentState, config: RunnableConfig) -> dict[str, Any]:
    ctx = get_test_context(config)
    page = ctx.page
    if page is None:
        raise RuntimeError("Playwright page not initialized")

    failures = list(state.get("failures_encountered") or [])
    if not failures:
        return {}

    last = failures[-1]
    step = last.get("step") or {}
    selector = step.get("selector")
    description = step.get("description") or selector or "interactive element"

    screenshot = await capture_screenshot_base64(page)
    raw = await vision_analyzer.detect_element(
        element_description=description,
        screenshot_base64=screenshot,
        llm_client=ctx.llm_client,
        session_id=ctx.session_id,
        test_id=ctx.test_id,
    )
    coords = vision_analyzer.parse_bounding_box(raw)
    click_point = vision_analyzer.translate_normalized_box(
        coords,
        settings.BROWSER_VIEWPORT_WIDTH,
        settings.BROWSER_VIEWPORT_HEIGHT,
    )
    await page.mouse.click(click_point["x"], click_point["y"])
    ctx.log_action("self_heal_click", x=click_point["x"], y=click_point["y"])

    selectors_db = dict(state.get("selectors_db") or {})
    if selector:
        selectors_db[selector] = f"coords:{click_point['x']},{click_point['y']}"

    return {
        "failures_encountered": [],
        "selectors_db": selectors_db,
        "current_step_index": max(0, state.get("current_step_index", 1) - 1),
    }
