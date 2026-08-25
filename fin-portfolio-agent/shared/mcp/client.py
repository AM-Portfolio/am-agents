"""
shared/mcp/client.py — Authenticated HTTP client for am-mcp-server.
"""
from __future__ import annotations
import logging, time
from typing import Any
import httpx
from shared.core.config import settings

logger = logging.getLogger(__name__)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

class McpUnavailableError(RuntimeError):
    """Raised when MCP is unreachable and AI_MCP_REQUIRED=true."""

class McpClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_token(self) -> str:
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
            resp.raise_for_status()
            body = resp.json()
        self._token = body["access_token"]
        self._token_expires_at = time.time() + int(body.get("expires_in", 300))
        return self._token

    def _hdrs(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": _UA}

    async def health_check(self) -> bool:
        try:
            token = await self._get_token()
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(f"{settings.MCP_BASE_URL}/health", headers=self._hdrs(token))
                return r.status_code in {200, 204}
        except Exception as e:
            logger.warning("mcp health_check failed: %s", e)
            return False

    async def _assert_healthy(self) -> None:
        if settings.AI_MCP_REQUIRED and not await self.health_check():
            raise McpUnavailableError("MCP unreachable and AI_MCP_REQUIRED=true")

    async def list_tools(self) -> list[dict[str, Any]]:
        await self._assert_healthy()
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{settings.MCP_BASE_URL}/tools", headers=self._hdrs(token))
            r.raise_for_status()
            return r.json()

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        await self._assert_healthy()
        token = await self._get_token()
        try:
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(f"{settings.MCP_BASE_URL}/tools/call",
                                 headers=self._hdrs(token), json={"name": name, "arguments": args})
                r.raise_for_status()
                return r.text
        except httpx.HTTPStatusError as e:
            err = f"MCP '{name}' HTTP {e.response.status_code}: {e.response.text[:200]}"
            logger.error(err); return f'{{"error": "{err}"}}'
        except Exception as e:
            err = f"MCP '{name}' failed: {e}"
            logger.error(err); return f'{{"error": "{err}"}}'

mcp_client = McpClient()
