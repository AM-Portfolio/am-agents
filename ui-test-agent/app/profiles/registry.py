"""Profile registry — central dispatch for test step builders."""
from __future__ import annotations

from typing import Any

from app.profiles.base import TargetConfig
from app.profiles.modern_ui.auth_flow import (
    auth_verification_checklist,
    build_auth_flow_steps,
)

AUTH_PROFILES = frozenset({"AUTH_FLOW", "AUTH_FLOW_MAIN", "AUTH_FLOW_PORTFOLIO"})


def profile_for_mode(ui_mode: str) -> str:
    return "AUTH_FLOW_MAIN" if ui_mode == "main" else "AUTH_FLOW_PORTFOLIO"


def build_profile_steps(
    profile: str,
    *,
    target_url: str,
    email: str,
    password: str,
    ui_mode: str,
    login_mode: str,
) -> list[dict[str, Any]]:
    return build_auth_flow_steps(
        target_url=target_url,
        email=email,
        password=password,
        profile=profile,
        ui_mode=ui_mode,
        login_mode=login_mode,
    )


def build_steps_from_target(
    target: TargetConfig,
    *,
    email: str,
    password: str,
) -> list[dict[str, Any]]:
    return build_profile_steps(
        target.profile,
        target_url=target.base_url,
        email=email,
        password=password,
        ui_mode=target.ui_mode,
        login_mode=target.auth_login_mode,
    )


def is_auth_profile(profile: str) -> bool:
    return profile in AUTH_PROFILES
