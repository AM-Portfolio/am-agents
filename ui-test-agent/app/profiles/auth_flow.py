"""Backward-compatible re-exports — prefer app.profiles.registry."""
from app.profiles.modern_ui.auth_flow import (
    auth_verification_checklist,
    build_auth_flow_steps,
    detect_ui_mode,
)
from app.profiles.registry import AUTH_PROFILES

__all__ = [
    "AUTH_PROFILES",
    "auth_verification_checklist",
    "build_auth_flow_steps",
    "detect_ui_mode",
]
