"""Authentication flow steps for am-modern-ui (Flutter web)."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def detect_ui_mode(target_url: str, profile: str, default_mode: str) -> str:
    host = urlparse(target_url).netloc.lower()
    if host in ("am.asrax.in",):
        return "main"
    if profile == "AUTH_FLOW_MAIN":
        return "main"
    if profile == "AUTH_FLOW_PORTFOLIO":
        return "portfolio"
    port = urlparse(target_url).port
    if port == 9000:
        return "main"
    if port in (9005, 8082):
        return "portfolio"
    return default_mode


def build_auth_flow_steps(
    *,
    target_url: str,
    email: str,
    password: str,
    profile: str,
    ui_mode: str,
    login_mode: str = "demo",
) -> list[dict[str, Any]]:
    mode = detect_ui_mode(target_url, profile, ui_mode)
    if mode == "main":
        return _main_app_auth_steps(target_url, email, password, login_mode)
    return _portfolio_auth_steps(target_url, email, password, login_mode)


def _login_steps(login_mode: str, email: str, password: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {
            "action": "wait_for_login",
            "timeout_ms": 60000,
            "name": "2. Wait for Flutter login form",
        },
        {"action": "screenshot", "name": "3. Screenshot — login form visible"},
    ]
    if login_mode == "demo":
        steps.extend(
            [
                {"action": "click_demo_login", "name": "4. Click Demo Login (login section)"},
                {"action": "screenshot", "name": "5. Screenshot — demo login triggered"},
            ]
        )
        return steps

    steps.extend(
        [
            {"action": "fill_label", "label": "Email", "text": email, "name": "4. Fill email"},
            {"action": "fill_label", "label": "Password", "text": password, "name": "5. Fill password"},
            {"action": "screenshot", "name": "6. Screenshot — credentials entered"},
            {"action": "click_button", "name_match": "Sign In", "name": "7. Click Sign In"},
        ]
    )
    return steps


def _portfolio_auth_steps(
    base_url: str, email: str, password: str, login_mode: str
) -> list[dict[str, Any]]:
    entry = base_url.rstrip("/") + "/"
    login = _login_steps(login_mode, email, password)
    wait_step = {
        "action": "wait",
        "ms": 6000,
        "name": "6. Wait for identity API + navigation"
        if login_mode == "demo"
        else "8. Wait for identity API + navigation",
    }
    post_login = [
        wait_step,
        {
            "action": "assert_url_contains",
            "pattern": "/portfolio/overview",
            "name": "7. Assert URL contains /portfolio/overview"
            if login_mode == "demo"
            else "9. Assert URL contains /portfolio/overview",
        },
        {
            "action": "assert_text_visible",
            "texts": ["Overview"],
            "name": "8. Assert Overview nav visible"
            if login_mode == "demo"
            else "10. Assert Overview nav visible",
        },
        {
            "action": "assert_text_visible",
            "texts": ["New Trade"],
            "name": "9. Assert New Trade action visible"
            if login_mode == "demo"
            else "11. Assert New Trade action visible",
        },
        {
            "action": "assert_title_not_empty",
            "name": "10. Assert browser title set"
            if login_mode == "demo"
            else "12. Assert browser title set",
        },
        {
            "action": "screenshot",
            "name": "11. Screenshot — authenticated portfolio shell"
            if login_mode == "demo"
            else "13. Screenshot — authenticated portfolio shell",
        },
    ]
    return [
        {
            "action": "navigate",
            "url": entry,
            "name": "1. Open portfolio app root (SPA; client routes to overview after login)",
        },
        *login,
        *post_login,
    ]


def _main_app_auth_steps(
    base_url: str, email: str, password: str, login_mode: str
) -> list[dict[str, Any]]:
    entry = base_url.rstrip("/") + "/"
    login = _login_steps(login_mode, email, password)
    wait_step = {
        "action": "wait",
        "ms": 6000,
        "name": "6. Wait for auth + redirect to /home"
        if login_mode == "demo"
        else "7. Wait for auth + redirect to /home",
    }
    post_login = [
        wait_step,
        {
            "action": "assert_url_contains",
            "pattern": "/home",
            "name": "7. Assert URL contains /home"
            if login_mode == "demo"
            else "8. Assert URL contains /home",
        },
        {
            "action": "assert_text_visible",
            "texts": ["Dashboard"],
            "name": "8. Assert Dashboard visible"
            if login_mode == "demo"
            else "9. Assert Dashboard visible",
        },
        {
            "action": "assert_text_visible",
            "texts": ["Portfolio"],
            "name": "9. Assert Portfolio nav visible"
            if login_mode == "demo"
            else "10. Assert Portfolio nav visible",
        },
        {
            "action": "screenshot",
            "name": "10. Screenshot — authenticated main shell"
            if login_mode == "demo"
            else "11. Screenshot — authenticated main shell",
        },
    ]
    return [
        {"action": "navigate", "url": entry, "name": "1. Open main AM app home"},
        *login,
        *post_login,
    ]


def auth_verification_checklist(
    steps: list[dict[str, Any]], action_log: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Build human-readable checklist for HTML report."""
    completed = {entry.get("name", "") for entry in action_log if entry.get("action") != "assert_failed"}
    items: list[dict[str, str]] = []
    for step in steps:
        name = step.get("name") or step.get("action", "step")
        action = step.get("action", "")
        if action.startswith("assert_"):
            status = "PASS" if any(name in c or action in str(c) for c in completed) else "PENDING"
            failed = any(
                entry.get("action") == "assert_failed" and entry.get("step") == name
                for entry in action_log
            )
            if failed:
                status = "FAIL"
            elif any(entry.get("action") == "assert_pass" for entry in action_log):
                status = "PASS"
        else:
            status = "PASS" if name in completed or action in ("screenshot", "wait") else "SKIP"
        items.append({"name": name, "status": status})
    return items
