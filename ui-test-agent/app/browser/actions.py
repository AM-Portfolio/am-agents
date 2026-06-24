from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_DEMO_LOGIN_BUTTON = re.compile(r"Demo Login|Try Demo|Quick Login", re.IGNORECASE)


async def _enable_flutter_accessibility(page) -> None:
    """Flutter web hides semantics until the placeholder is activated."""
    await page.evaluate(
        """() => {
            const el = document.querySelector('flt-semantics-placeholder[aria-label="Enable accessibility"]');
            if (el) el.click();
        }"""
    )
    await page.wait_for_timeout(1500)


async def _wait_for_flutter(page, timeout_ms: int) -> None:
    await page.wait_for_load_state("load", timeout=min(timeout_ms, 90000))
    try:
        await page.wait_for_function(
            """() => {
                const pane = document.querySelector('flt-glass-pane')
                    || document.querySelector('flutter-view')
                    || document.querySelector('flt-scene-host');
                if (!pane) return false;
                const rect = pane.getBoundingClientRect();
                return rect.width > 100 && rect.height > 100;
            }""",
            timeout=min(timeout_ms, 90000),
        )
    except Exception:
        pass
    await page.wait_for_timeout(5000)


async def _wait_for_login_form(page, timeout_ms: int) -> None:
    import time

    await _wait_for_flutter(page, timeout_ms)
    await _enable_flutter_accessibility(page)
    deadline = time.monotonic() + (timeout_ms / 1000)
    locators = [
        page.get_by_label(re.compile(r"email", re.I)),
        page.get_by_placeholder("Enter your email"),
        page.get_by_placeholder("Email / User ID"),
        page.get_by_role("textbox").first,
        page.get_by_role("button", name=re.compile(r"Sign In|Developer Options|Demo Login|Try Demo", re.I)),
        page.get_by_text(re.compile(r"Portfolio Login|Welcome Back|Forgot Password", re.I)),
    ]
    last_error = "Login form not visible"
    while time.monotonic() < deadline:
        for locator in locators:
            try:
                if await locator.count() > 0 and await locator.first.is_visible():
                    return
            except Exception as exc:
                last_error = str(exc)
        await page.wait_for_timeout(750)
    raise TimeoutError(f"Login form not visible after {timeout_ms}ms: {last_error}")


async def _click_demo_login(page) -> None:
    """Click visible Demo Login, or expand Developer Options then Try Demo Version."""
    for pattern in (_DEMO_LOGIN_BUTTON,):
        button = page.get_by_role("button", name=pattern).first
        try:
            if await button.is_visible():
                await button.click(timeout=20000)
                return
        except Exception:
            pass

    dev_options = page.get_by_role("button", name=re.compile(r"Developer Options", re.IGNORECASE)).first
    await dev_options.click(timeout=20000)
    await page.wait_for_timeout(500)
    await page.get_by_role("button", name=_DEMO_LOGIN_BUTTON).first.click(timeout=20000)


async def run_browser_action(page, step: dict[str, Any], ctx) -> None:
    action = step.get("action")
    name = step.get("name", action)

    if action == "navigate":
        url = step["url"]
        logger.info("[%s] Navigate → %s", name, url)
        response = await page.goto(url, wait_until="load", timeout=90000)
        if response and response.status >= 400 and not step.get("allow_http_error"):
            raise RuntimeError(f"Navigation failed HTTP {response.status} for {url}")
        ctx.log_action("navigate", step=name, url=url, status=response.status if response else None)

    elif action == "wait":
        ms = int(step.get("ms", 1000))
        await page.wait_for_timeout(ms)
        ctx.log_action("wait", step=name, ms=ms)

    elif action == "wait_for_label":
        label = step["label"]
        timeout = int(step.get("timeout_ms", 30000))
        logger.info("[%s] Waiting for label %r", name, label)
        await page.get_by_label(label).first.wait_for(state="visible", timeout=timeout)
        ctx.log_action("wait_for_label", step=name, label=label)

    elif action == "wait_for_flutter":
        timeout = int(step.get("timeout_ms", 60000))
        logger.info("[%s] Waiting for Flutter web bootstrap", name)
        await _wait_for_flutter(page, timeout)
        ctx.log_action("wait_for_flutter", step=name, timeout_ms=timeout)

    elif action == "wait_for_login":
        timeout = int(step.get("timeout_ms", 45000))
        logger.info("[%s] Waiting for login form", name)
        await _wait_for_login_form(page, timeout)
        ctx.log_action("wait_for_login", step=name, timeout_ms=timeout)

    elif action == "fill_label":
        label = step["label"]
        text = step["text"]
        logger.info("[%s] Fill label %r", name, label)
        await page.get_by_label(label).first.fill(text, timeout=15000)
        ctx.log_action("fill_label", step=name, label=label)

    elif action == "click_button":
        name_match = step.get("name_match", step.get("text", ""))
        logger.info("[%s] Click button matching %r", name, name_match)
        pattern = re.compile(name_match, re.IGNORECASE)
        await page.get_by_role("button", name=pattern).first.click(timeout=20000)
        ctx.log_action("click_button", step=name, button=name_match)

    elif action == "click_demo_login":
        logger.info("[%s] Click Demo Login (login section)", name)
        await _click_demo_login(page)
        ctx.log_action("click_demo_login", step=name)

    elif action == "click":
        selector = step["selector"]
        await page.click(selector, timeout=15000)
        ctx.log_action("click", step=name, selector=selector)

    elif action == "fill":
        await page.fill(step["selector"], step["text"], timeout=15000)
        ctx.log_action("fill", step=name, selector=step["selector"])

    elif action == "screenshot":
        ctx.log_action("screenshot", step=name)

    elif action.startswith("assert_"):
        pass

    else:
        raise ValueError(f"Unknown step action: {action}")
