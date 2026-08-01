from __future__ import annotations

from pathlib import Path

from tools._base_plugin import BaseIntegrationTool


class K8sTool(BaseIntegrationTool):
    """Kubernetes capability tool routing to kagent-tool-server MCP."""
    pass


def get_tool() -> K8sTool:
    return K8sTool(Path(__file__).resolve().parent)
