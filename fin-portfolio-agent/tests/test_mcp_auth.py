import pytest

from shared.context.request_context import auth_token_var
from shared.mcp_ext.client import McpClient


@pytest.mark.asyncio
async def test_get_token_prefers_user_jwt_over_gateway_skip(monkeypatch):
    monkeypatch.setattr(
        "shared.mcp_ext.client.settings.MCP_GATEWAY_AUTH_DISABLED",
        True,
    )
    auth_token_var.set("Bearer user-jwt-token")
    client = McpClient()
    assert await client._get_token() == "user-jwt-token"


@pytest.mark.asyncio
async def test_get_token_returns_empty_when_no_user_jwt_and_auth_disabled(monkeypatch):
    monkeypatch.setattr(
        "shared.mcp_ext.client.settings.MCP_GATEWAY_AUTH_DISABLED",
        True,
    )
    auth_token_var.set("")
    client = McpClient()
    assert await client._get_token() == ""


@pytest.mark.asyncio
async def test_get_token_required_raises_for_user_scoped_tools(monkeypatch):
    monkeypatch.setattr(
        "shared.mcp_ext.client.settings.MCP_GATEWAY_AUTH_DISABLED",
        True,
    )
    auth_token_var.set("")
    client = McpClient()
    with pytest.raises(Exception) as exc:
        await client._get_token(required=True)
    assert "Authorization Bearer JWT" in str(exc.value)
