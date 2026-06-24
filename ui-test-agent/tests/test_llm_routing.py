from unittest.mock import patch

import pytest

from app.config import Settings


def test_direct_routing_requires_master_key():
    with pytest.raises(ValueError, match="LITELLM_MASTER_KEY"):
        Settings(
            LLM_ROUTING="direct",
            APP_ENV="preprod",
            LITELLM_MASTER_KEY=None,
        )


def test_direct_routing_blocked_in_production():
    with pytest.raises(ValueError, match="not allowed"):
        Settings(
            LLM_ROUTING="direct",
            APP_ENV="production",
            LITELLM_MASTER_KEY="sk-test",
        )


def test_factory_returns_litellm_client():
    from app.llm.factory import create_llm_client
    from app.llm.litellm_client import LiteLLMClient

    cfg = Settings(
        LLM_ROUTING="direct",
        APP_ENV="preprod",
        LITELLM_MASTER_KEY="sk-test",
    )
    with patch("app.llm.factory.settings", cfg):
        client = create_llm_client()
    assert isinstance(client, LiteLLMClient)


def test_factory_returns_gateway_client():
    from app.llm.factory import create_llm_client
    from app.llm.gateway_client import GatewayLLMClient

    cfg = Settings(
        LLM_ROUTING="gateway",
        APP_ENV="preprod",
    )
    with patch("app.llm.factory.settings", cfg):
        client = create_llm_client()
    assert isinstance(client, GatewayLLMClient)
