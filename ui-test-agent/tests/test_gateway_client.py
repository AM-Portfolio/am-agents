from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.gateway_client import GatewayLLMClient


@pytest.mark.asyncio
async def test_gateway_chat_text():
    client = GatewayLLMClient()
    client.base_url = "http://gateway.test"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": "hello",
        "model": "deepseek-chat",
        "sessionId": "s1",
        "traceId": "t1",
    }

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    with patch.object(client, "_get_access_token", return_value=None):
        with patch("app.llm.gateway_client.settings") as mock_settings:
            mock_settings.MCP_GATEWAY_AUTH_DISABLED = True
            mock_settings.LLM_TEMPERATURE = 0.2
            mock_settings.LLM_MAX_TOKENS = 2048
            mock_settings.LLM_TIMEOUT_SECONDS = 30.0
            with patch("app.llm.gateway_client.httpx.AsyncClient", return_value=mock_http):
                text = await client.chat_text(
                    system="sys",
                    user="hi",
                    model="deepseek-chat",
                    session_id="s1",
                    test_id="test-1",
                )

    assert text == "hello"
    mock_http.post.assert_called_once()
    call_kwargs = mock_http.post.call_args.kwargs
    assert call_kwargs["json"]["source"] == "ui-test-agent"
    assert call_kwargs["json"]["testId"] == "test-1"
