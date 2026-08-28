"""
Resolve MCP HTTP/SSE URLs from MCP_BASE_URL.

Public ingress:  https://am.asrax.in/mcp  → /mcp/sse
In-cluster pod:  http://am-mcp-server:8080 → /sse (no /mcp prefix on the pod)
"""
from __future__ import annotations

from urllib.parse import urlparse

from shared.core.config import settings


def normalize_mcp_base_url(raw: str | None = None) -> str:
    """Strip trailing slashes and accidental /sse suffix only."""
    url = (raw or settings.MCP_BASE_URL or "").strip().rstrip("/")
    if url.endswith("/sse"):
        url = url[:-4]
    return url.rstrip("/")


def resolve_mcp_sse_url(base: str | None = None) -> str:
    """
    SSE endpoint for the official MCP Python SDK.
    """
    root = normalize_mcp_base_url(base)
    if not root:
        raise ValueError("MCP_BASE_URL is not configured")
    if root.endswith("/mcp"):
        return f"{root}/sse"
    return f"{root}/sse"


def resolve_mcp_health_url(base: str | None = None) -> str:
    """Spring Boot actuator health at pod root (/actuator/health)."""
    root = normalize_mcp_base_url(base)
    if not root:
        raise ValueError("MCP_BASE_URL is not configured")
    # Ingress-style .../mcp base → health is on the host root, not under /mcp
    host_root = root[:-4] if root.endswith("/mcp") else root
    parsed = urlparse(host_root)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/actuator/health"
    return f"{host_root}/actuator/health"
