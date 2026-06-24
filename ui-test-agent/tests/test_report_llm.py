"""Tests for LLM-generated release narrative."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.report_llm import generate_llm_report
from app.agent.report_metrics import render_report_html
from app.context import TestRunContext


def _ctx() -> TestRunContext:
    return TestRunContext(
        test_id="abc-123",
        session_id="ui-test-abc",
        profile="AUTH_FLOW_MAIN",
        llm_client=MagicMock(),
        branch="main",
    )


def _sample_document() -> dict:
    return {
        "test_id": "abc-123",
        "profile": "AUTH_FLOW_MAIN",
        "target_url": "https://example.com",
        "status": "PASSED",
        "release_gate": {
            "decision": "BASELINE_SEEDED",
            "headline": "Baselines captured for future compare",
            "rationale": "Seed mode — no drift comparison yet.",
            "blockers": [],
            "gates": [],
            "llm_vision_calls": 0,
        },
        "results": {
            "checklist_pass": 5,
            "checklist_total": 5,
            "failure_count": 0,
            "failures": [],
        },
        "timing": {"total_duration_human": "12.3s"},
        "design_review": {
            "baseline_mode": "seed",
            "overall_verdict": "pass",
            "screenshots": [],
        },
    }


def test_parse_llm_json_extracts_object_from_prose():
    from app.agent.report_llm import _parse_llm_json

    raw = (
        "Here is the summary:\n\n"
        '{"executive_summary":"ok","release_recommendation":"go","risks":[],"next_steps":[],"stakeholder_note":"fine"}'
    )
    data = _parse_llm_json(raw)
    assert data["executive_summary"] == "ok"


@pytest.mark.asyncio
async def test_generate_llm_report_parses_json():
    ctx = _ctx()
    llm_json = json.dumps(
        {
            "executive_summary": "Auth flow passed.",
            "release_recommendation": "Seed baselines before next release.",
            "risks": ["No compare-mode drift check yet."],
            "next_steps": ["Run compare mode on next build."],
            "stakeholder_note": "Login works; visual baselines saved.",
        }
    )
    ctx.llm_client.chat_text = AsyncMock(return_value=llm_json)

    with patch("app.agent.report_llm.settings.REPORT_LLM_ENABLED", True):
        with patch("app.agent.report_llm.settings.REPORT_LLM_VISION", False):
            result = await generate_llm_report(ctx, _sample_document(), llm_client=ctx.llm_client)

    assert result["generated"] is True
    assert result["executive_summary"] == "Auth flow passed."
    assert result["risks"] == ["No compare-mode drift check yet."]
    ctx.llm_client.chat_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_llm_report_fallback_when_disabled():
    ctx = _ctx()
    with patch("app.agent.report_llm.settings.REPORT_LLM_ENABLED", False):
        result = await generate_llm_report(ctx, _sample_document(), llm_client=ctx.llm_client)
    assert result["generated"] is False
    assert result["fallback"] is True
    assert "REPORT_LLM_ENABLED=false" in result["error"]


def test_render_report_html_includes_llm_section():
    doc = _sample_document()
    doc.update(
        {
            "timing": {
                "total_duration_human": "12.3s",
                "step_count": 1,
                "avg_step_ms": 100,
                "slowest_step": {},
                "assert_pass_count": 1,
                "assert_fail_count": 0,
            },
            "results": {
                **doc["results"],
                "passed": True,
                "checklist": [],
                "final_url": "https://example.com/#/home",
            },
            "environment": {"baseline_mode": "seed"},
            "llm_report": {
                "generated": True,
                "fallback": False,
                "model": "deepseek-chat",
                "executive_summary": "All checks passed.",
                "release_recommendation": "Proceed after baseline seed.",
                "risks": [],
                "next_steps": ["Switch to compare mode."],
                "stakeholder_note": "Ready for baseline capture.",
            },
        }
    )
    html = render_report_html(doc, screenshots_html="<p>none</p>")
    assert "Release narrative (LLM)" in html
    assert "All checks passed." in html
    assert "AI-generated" in html
