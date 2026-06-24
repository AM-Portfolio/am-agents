"""Shared types for test profile plugins."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TargetConfig:
    """Resolved test target from a wrapper targets file or agent settings."""

    base_url: str
    ui_mode: Literal["portfolio", "main"] = "portfolio"
    auth_login_mode: Literal["demo", "credentials"] = "demo"
    profile: str = "AUTH_FLOW_PORTFOLIO"
    module: str = "modern-ui"
    environment: str = "preprod"
