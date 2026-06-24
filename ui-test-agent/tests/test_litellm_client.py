from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.litellm_client import LiteLLMClient


@pytest.mark.asyncio
async def test_litellm_direct_chat_text():
    client = LiteLLMClient()
    client.base_url = "http://litellm.test"
    client.api_key = "sk-test"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "4"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    with patch("app.llm.litellm_client.settings") as mock_settings:
        mock_settings.LLM_TEMPERATURE = 0.2
        mock_settings.LLM_MAX_TOKENS = 2048
        mock_settings.LLM_TIMEOUT_SECONDS = 30.0
        with patch("app.llm.litellm_client.httpx.AsyncClient", return_value=mock_http):
            text = await client.chat_text(
                system="sys",
                user="hi",
                model="deepseek-chat",
                session_id="s1",
                test_id="test-1",
            )

    assert text == "4"
    call_kwargs = mock_http.post.call_args.kwargs
    assert call_kwargs["json"]["metadata"]["test_id"] == "test-1"
    assert call_kwargs["json"]["metadata"]["source"] == "ui-test-agent"
