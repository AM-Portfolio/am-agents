"""
shared/mcp/client.py — Authenticated HTTP client for am-mcp-server.
"""
from __future__ import annotations
import logging, time, json
from typing import Any
import httpx
from shared.context.request_context import auth_token_var
from shared.core.config import settings
from shared.mcp_ext.urls import resolve_mcp_health_url, resolve_mcp_sse_url
from shared.observability.agent_log import log_agent_debug, log_agent_error, log_agent_event, log_agent_warning
from shared.observability.log_events import AgentLogEvent
from shared.observability.logging_setup import get_logger

logger = get_logger("mcp")
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

class McpUnavailableError(RuntimeError):
    """Raised when MCP is unreachable and AI_MCP_REQUIRED=true."""


class McpAuthRequiredError(RuntimeError):
    """Raised when a user-scoped MCP tool is called without an inbound JWT."""

class McpClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    @staticmethod
    def _user_bearer_token() -> str:
        """End-user JWT forwarded from UI → gateway → fin-agent Authorization header."""
        from shared.context.jwt_context import bearer_token

        return bearer_token(auth_token_var.get() or "")

    async def _get_token(self, *, required: bool = False) -> str:
        user_token = self._user_bearer_token()
        if user_token:
            return user_token

        # In-cluster: skip Keycloak client-credentials hop when disabled, but MCP
        # server /sse still requires a JWT — caller must forward user auth above.
        if settings.MCP_GATEWAY_AUTH_DISABLED:
            if required:
                raise McpAuthRequiredError(
                    "Portfolio and account tools require your login session (Authorization Bearer JWT). "
                    "Please sign in again and retry."
                )
            return ""

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
            log_agent_warning(
                logger,
                AgentLogEvent.MCP_HEALTH_FAIL,
                error=e,
                url=settings.MCP_BASE_URL,
            )
            return False

    async def _assert_healthy(self) -> None:
        if settings.AI_MCP_REQUIRED and not await self.health_check():
            raise McpUnavailableError("MCP unreachable and AI_MCP_REQUIRED=true")

    async def list_tools(self) -> list[dict[str, Any]]:
        # Not strictly needed by the agent since it reads from tools.py
        # but provided for completeness.
        return []

    _USER_SCOPED_TOOLS = frozenset({
        "get_portfolio_summary",
        "get_holdings_list",
        "get_holding_detail",
        "get_sector_allocation",
        "get_benchmark_comparison",
        "get_basket_list",
        "get_trade_history",
        "get_recent_activity",
        "analyze_etf_overlap",
        "count_etfs",
        "get_risk_metrics",
        "get_performance_chart",
        "place_order",
        "modify_order",
        "cancel_order",
        "create_basket",
    })

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        await self._assert_healthy()
        user_scoped = name in self._USER_SCOPED_TOOLS
        try:
            token = await self._get_token(required=user_scoped)
        except McpAuthRequiredError as exc:
            err = str(exc)
            log_agent_error(logger, AgentLogEvent.MCP_CALL_ERROR, error=err, tool=name)
            return json.dumps({"ok": False, "error": "AUTH_REQUIRED", "message": err})

        headers = {"User-Agent": _UA}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = resolve_mcp_sse_url()
        from shared.context.jwt_context import jwt_subject

        jwt_user = jwt_subject(token) if token else None
        log_agent_event(
            logger,
            AgentLogEvent.MCP_CALL_START,
            tool=name,
            args=args,
            sse_url=url,
            jwt_user_id=jwt_user or "-",
        )

        try:
            async with sse_client(url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, args)

                    if result.is_error:
                        err = f'MCP Tool error: {result}'
                        log_agent_error(
                            logger,
                            AgentLogEvent.MCP_CALL_ERROR,
                            error=err,
                            tool=name,
                        )
                        return f'{{"error": "{err}"}}'

                    text_parts = [content.text for content in result.content if hasattr(content, "text")]
                    output = "\n".join(text_parts)
                    log_agent_event(
                        logger,
                        AgentLogEvent.MCP_CALL_END,
                        tool=name,
                        result_preview=output[:200],
                    )
                    return output

        except httpx.HTTPStatusError as e:
            err = f"MCP '{name}' HTTP {e.response.status_code}: {e.response.text[:200]}"
            log_agent_error(logger, AgentLogEvent.MCP_CALL_ERROR, error=err, tool=name)
            return f'{{"error": "{err}"}}'
        except Exception as e:
            err = f"MCP '{name}' failed: {e}"
            log_agent_error(
                logger,
                AgentLogEvent.MCP_CALL_ERROR,
                error=e,
                tool=name,
                exc_info=True,
            )
            return f'{{"error": "{err}"}}'

mcp_client = McpClient()
