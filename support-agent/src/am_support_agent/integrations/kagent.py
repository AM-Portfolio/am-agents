"""Kagent / MCP integration notes — not part of the orchestrator binary.

Kagent agents call Tool Agent via the MCP bridge (:8085). Support-agent
talks to Tool Agent via HTTP adapters. Two entry paths, one preferred executor.
"""

from __future__ import annotations

import os
from typing import Any


def kagent_integration_status() -> dict[str, Any]:
    mcp_url = (
        os.getenv("TOOL_AGENT_MCP_URL", "").strip()
        or os.getenv("SUPPORT_AGENT_KAGENT_MCP_URL", "").strip()
        or "http://127.0.0.1:8085"
    )
    return {
        "optional": True,
        "in_orchestrator_binary": False,
        "mcp_url": mcp_url,
        "executor": "tool-agent",
        "manifest_path": "k8s/kagent/",
        "note": (
            "Keep k8s/kagent as the MCP entry to Tool Agent. Support-agent "
            "does not embed kagent; document URL only for operators."
        ),
    }


__all__ = ["kagent_integration_status"]
