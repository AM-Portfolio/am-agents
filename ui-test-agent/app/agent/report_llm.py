"""LLM-generated release narrative for UI test reports."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from app.context import TestRunContext
    from app.llm.base import LLMClient

logger = logging.getLogger(__name__)

_REPORT_SYSTEM = """You are a release QA lead writing a go/no-go summary for a Flutter web app UI test.
Use ONLY the structured test data provided. Be concise and actionable for engineering and product.
Return ONLY valid JSON (no markdown):
{
  "executive_summary": "2-3 sentences",
  "release_recommendation": "one clear sentence for go/no-go",
  "risks": ["bullet", "..."],
  "next_steps": ["bullet", "..."],
  "stakeholder_note": "one paragraph plain language for non-engineers"
}"""


def _compact_document(document: dict[str, Any]) -> dict[str, Any]:
    design = document.get("design_review") or {}
    shots = design.get("screenshots") or []
    return {
        "test_id": document.get("test_id"),
        "profile": document.get("profile"),
        "target_url": document.get("target_url"),
        "status": document.get("status"),
        "release_decision": (document.get("release_gate") or {}).get("decision"),
        "release_headline": (document.get("release_gate") or {}).get("headline"),
        "baseline_mode": design.get("baseline_mode"),
        "design_verdict": design.get("overall_verdict"),
        "checklist_pass": (document.get("results") or {}).get("checklist_pass"),
        "checklist_total": (document.get("results") or {}).get("checklist_total"),
        "failure_count": (document.get("results") or {}).get("failure_count"),
        "duration": (document.get("timing") or {}).get("total_duration_human"),
        "screenshots_reviewed": len(shots),
        "llm_vision_calls": (document.get("release_gate") or {}).get("llm_vision_calls"),
        "design_screens": [
            {
                "step": s.get("step_label"),
                "verdict": s.get("verdict"),
                "similarity": s.get("similarity"),
                "summary": s.get("llm_summary"),
            }
            for s in shots
        ],
        "failures": (document.get("results") or {}).get("failures") or [],
        "gates": (document.get("release_gate") or {}).get("gates") or [],
    }


def _parse_llm_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if not cleaned:
        raise ValueError("LLM returned empty response")

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    candidates = [cleaned]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        candidates.append(cleaned[start : end + 1])

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
            last_error = ValueError("LLM report must be a JSON object")
        except json.JSONDecodeError as exc:
            last_error = exc

    raise ValueError(f"Could not parse LLM JSON: {last_error}")


def _fallback_narrative(document: dict[str, Any], *, reason: str) -> dict[str, Any]:
    gate = document.get("release_gate") or {}
    decision = gate.get("decision", document.get("status", "UNKNOWN"))
    return {
        "generated": False,
        "fallback": True,
        "error": reason,
        "model": None,
        "executive_summary": (
            f"UI test {document.get('test_id', '')} finished with status {document.get('status')} "
            f"and release decision {decision}. LLM narrative unavailable ({reason})."
        ),
        "release_recommendation": gate.get("headline") or str(decision),
        "risks": [b["detail"] for b in gate.get("blockers") or []] or [],
        "next_steps": [
            "Review HTML report and baseline screenshots manually.",
            "Re-run with REPORT_LLM_ENABLED after LiteLLM is reachable.",
        ],
        "stakeholder_note": gate.get("rationale") or "",
        "visual_assessment": None,
        "usage": {},
    }


async def generate_llm_report(
    ctx: TestRunContext,
    document: dict[str, Any],
    *,
    llm_client: LLMClient,
    final_screenshot_b64: str | None = None,
) -> dict[str, Any]:
    if not settings.REPORT_LLM_ENABLED:
        return _fallback_narrative(document, reason="REPORT_LLM_ENABLED=false")

    payload = _compact_document(document)
    user_prompt = (
        "Write the release QA JSON summary for this UI test run:\n\n"
        f"{json.dumps(payload, indent=2, default=str)}"
    )

    result: dict[str, Any] = {
        "generated": False,
        "fallback": False,
        "model": settings.LLM_PLANNER_MODEL,
        "usage": {},
    }

    try:
        raw = await llm_client.chat_text(
            system=_REPORT_SYSTEM,
            user=user_prompt,
            model=settings.LLM_PLANNER_MODEL,
            session_id=ctx.session_id,
            test_id=ctx.test_id,
            temperature=0.2,
        )
        parsed = _parse_llm_json(raw)
        result.update(parsed)
        result["generated"] = True
        result["model"] = settings.LLM_PLANNER_MODEL
    except Exception as exc:
        logger.warning("LLM report narrative failed: %s", exc)
        return _fallback_narrative(document, reason=str(exc))

    if settings.REPORT_LLM_VISION and final_screenshot_b64:
        try:
            vision_prompt = (
                "You are a UI release reviewer. Describe the authenticated app shell in this screenshot "
                "for a release report: layout health, visible nav/content, any obvious issues. "
                "Return 2-4 sentences plain text only."
            )
            visual = await llm_client.chat_vision(
                prompt=vision_prompt,
                screenshot_base64=final_screenshot_b64,
                model=settings.LLM_VISION_MODEL,
                session_id=ctx.session_id,
                test_id=ctx.test_id,
            )
            result["visual_assessment"] = visual.strip()
            result["vision_model"] = settings.LLM_VISION_MODEL
        except Exception as exc:
            logger.warning("LLM visual assessment failed: %s", exc)
            result["visual_assessment_error"] = str(exc)

    return result
