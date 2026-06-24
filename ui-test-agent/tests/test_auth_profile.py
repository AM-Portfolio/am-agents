from app.config import Settings
from app.profiles.auth_flow import AUTH_PROFILES, build_auth_flow_steps, detect_ui_mode


def test_auth_profiles_defined():
    assert "AUTH_FLOW" in AUTH_PROFILES
    assert "AUTH_FLOW_PORTFOLIO" in AUTH_PROFILES


def test_portfolio_auth_steps_demo_login():
    steps = build_auth_flow_steps(
        target_url="http://localhost:9005",
        email="user@test.com",
        password="secret",
        profile="AUTH_FLOW",
        ui_mode="portfolio",
        login_mode="demo",
    )
    assert steps[0]["action"] == "navigate"
    assert steps[0]["url"].endswith("/")
    assert any(s["action"] == "click_demo_login" for s in steps)
    assert any(s["action"] == "wait_for_login" for s in steps)
    assert not any(s["action"] == "fill_label" for s in steps)
    assert any(s["action"] == "assert_text_visible" for s in steps)


def test_portfolio_auth_steps_credentials():
    steps = build_auth_flow_steps(
        target_url="http://localhost:9005",
        email="user@test.com",
        password="secret",
        profile="AUTH_FLOW",
        ui_mode="portfolio",
        login_mode="credentials",
    )
    assert any(s["action"] == "fill_label" and s["label"] == "Email" for s in steps)
    assert any(s["action"] == "click_button" for s in steps)


def test_main_auth_steps_by_profile():
    steps = build_auth_flow_steps(
        target_url="http://localhost:9000",
        email="a@b.com",
        password="x",
        profile="AUTH_FLOW_MAIN",
        ui_mode="portfolio",
        login_mode="demo",
    )
    assert any("/home" in s.get("pattern", "") for s in steps if s["action"] == "assert_url_contains")


def test_detect_ui_mode_from_port():
    assert detect_ui_mode("http://localhost:9000", "AUTH_FLOW", "portfolio") == "main"
    assert detect_ui_mode("http://localhost:9005", "AUTH_FLOW", "main") == "portfolio"


import pytest

from app.agent import planner as planner_mod
from app.config import Settings


@pytest.mark.asyncio
async def test_planner_uses_auth_profile_without_llm(monkeypatch):
    cfg = Settings(
        LLM_ROUTING="direct",
        APP_ENV="preprod",
        LITELLM_MASTER_KEY="sk-test",
        AUTH_LOGIN_MODE="demo",
    )
    monkeypatch.setattr(planner_mod, "settings", cfg)

    class FakeCtx:
        profile = "AUTH_FLOW_PORTFOLIO"
        session_id = "s1"
        test_id = "t1"

        class llm_client:
            @staticmethod
            async def chat_text(**kwargs):
                raise AssertionError("LLM should not be called for AUTH profile")

    steps = await planner_mod.plan_steps(
        target_url="http://localhost:9005",
        specification="",
        profile="AUTH_FLOW_PORTFOLIO",
        ctx=FakeCtx(),
    )
    assert len(steps) >= 10
    assert any(s["action"] == "click_demo_login" for s in steps)
