"""
shared/mcp/client.py — Authenticated HTTP client for am-mcp-server.
"""
from __future__ import annotations
import logging, time
from typing import Any
import httpx
from shared.core.config import settings
from shared.mcp_ext.urls import resolve_mcp_health_url, resolve_mcp_sse_url

logger = logging.getLogger(__name__)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

class McpUnavailableError(RuntimeError):
    """Raised when MCP is unreachable and AI_MCP_REQUIRED=true."""

class McpClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_token(self) -> str:
        if settings.MCP_GATEWAY_AUTH_DISABLED:
            return ""  # no auth needed for internal cluster pod-to-pod routing
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token
        token_url = (
            settings.KEYCLOAK_TOKEN_URL
            or "https://auth.asrax.in/auth/realms/am-realm/protocol/openid-connect/token"
        )
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.post(
                token_url,
                data={"grant_type": "client_credentials",
                      "client_id": settings.AM_MCP_CLIENT_ID,
                      "client_secret": settings.AM_MCP_CLIENT_SECRET or ""},
                headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": _UA},
            )
            if resp.status_code != 200:
                logger.error("Failed to get MCP token: %s", resp.text)
            resp.raise_for_status()
            body = resp.json()
        self._token = body["access_token"]
        self._token_expires_at = time.time() + int(body.get("expires_in", 300))
        return self._token

    async def health_check(self) -> bool:
        try:
            health_url = resolve_mcp_health_url()
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(health_url)
                return r.status_code in {200, 204}
        except Exception as e:
            logger.warning("mcp health_check failed url=%s err=%s", settings.MCP_BASE_URL, e)
            return False

    async def _assert_healthy(self) -> None:
        if settings.AI_MCP_REQUIRED and not await self.health_check():
            raise McpUnavailableError("MCP unreachable and AI_MCP_REQUIRED=true")

    async def list_tools(self) -> list[dict[str, Any]]:
        # Not strictly needed by the agent since it reads from tools.py
        # but provided for completeness.
        return []

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        await self._assert_healthy()
        token = await self._get_token()
        headers = {"User-Agent": _UA}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        url = resolve_mcp_sse_url()
        logger.debug("mcp call_tool name=%s sse_url=%s", name, url)

        try:
            async with sse_client(url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, args)
                    
                    # MCP SDK returns CallToolResult. We need to extract the text.
                    if result.is_error:
                        return f'{{"error": "MCP Tool error: {result}"}}'
                    
                    # Join all TextContent parts
                    text_parts = [content.text for content in result.content if hasattr(content, 'text')]
                    return "\n".join(text_parts)
                    
        except httpx.HTTPStatusError as e:
            err = f"MCP '{name}' HTTP {e.response.status_code}: {e.response.text[:200]}"
            logger.error(err); return f'{{"error": "{err}"}}'
        except Exception as e:
            err = f"MCP '{name}' failed: {e}"
            logger.error(err); return f'{{"error": "{err}"}}'

mcp_client = McpClient()
