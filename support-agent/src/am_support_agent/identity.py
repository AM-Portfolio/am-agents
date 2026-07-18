"""Canonical support-agent identity for the parallel platform module."""

from __future__ import annotations

import os

# Stable machine id (matches tool-agent / db-agent / ui-test-agent style).
AGENT_ID = "support-agent"

# Human-facing label for tickets/chat (legacy ports used "IT-Support-agent").
DEFAULT_DISPLAY_NAME = "Support Agent"


def agent_id() -> str:
    return os.getenv("SUPPORT_AGENT_ID", AGENT_ID).strip() or AGENT_ID


def display_name() -> str:
    return (
        os.getenv("AGENT_DISPLAY_NAME")
        or os.getenv("SUPPORT_AGENT_DISPLAY_NAME")
        or DEFAULT_DISPLAY_NAME
    ).strip() or DEFAULT_DISPLAY_NAME
