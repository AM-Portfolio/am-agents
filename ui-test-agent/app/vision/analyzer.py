from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any, List

from app.config import settings

if TYPE_CHECKING:
    from app.llm.base import LLMClient

logger = logging.getLogger(__name__)

DESIGN_VERDICTS = frozenset(
    {
        "matches_baseline",
        "intentional_redesign",
        "layout_regression",
        "missing_content",
        "uncertain",
    }
)


class VisionAnalyzer:
    async def detect_element(
        self,
        *,
        element_description: str,
        screenshot_base64: str,
        llm_client: LLMClient,
        session_id: str,
        test_id: str,
    ) -> str:
        prompt = (
            f"Locate the element described as '{element_description}' on the screen. "
            "Return ONLY the normalized bounding box in format [ymin, xmin, ymax, xmax] "
            "in the range 0-1000. Do not return any extra text."
        )
        return await llm_client.chat_vision(
            prompt=prompt,
            screenshot_base64=screenshot_base64,
            model=settings.LLM_VISION_MODEL,
            session_id=session_id,
            test_id=test_id,
        )

    async def review_design_change(
        self,
        *,
        current_b64: str,
        baseline_b64: str | None,
        checklist: list[str],
        step_label: str,
        llm_client: LLMClient,
        session_id: str,
        test_id: str,
    ) -> dict[str, Any]:
        checklist_text = ", ".join(checklist) if checklist else "none recorded"
        prompt = (
            f"You are a UI QA reviewer for a Flutter web app. Step: '{step_label}'.\n"
            f"Functional checks already passed: {checklist_text}.\n"
            "Compare the CURRENT screenshot to the BASELINE (if provided).\n"
            "Return ONLY valid JSON:\n"
            '{"verdict":"matches_baseline|intentional_redesign|layout_regression|'
            'missing_content|uncertain","confidence":0.0,"summary":"one sentence",'
            '"issues":[]}\n'
            "Use intentional_redesign for coherent visual refresh with working layout.\n"
            "Use layout_regression for overlap, clipping, broken alignment, or unreadable UI.\n"
            "Use missing_content when expected nav/content from checklist is visually absent."
        )
        content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if baseline_b64:
            content_parts.append(
                {
                    "type": "text",
                    "text": "BASELINE screenshot (approved design):",
                }
            )
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{baseline_b64}"},
                }
            )
        content_parts.append({"type": "text", "text": "CURRENT screenshot:"})
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{current_b64}"},
            }
        )
        messages = [{"role": "user", "content": content_parts}]
        try:
            body = await llm_client.chat_completions(
                messages,
                model=settings.LLM_VISION_MODEL,
                session_id=session_id,
                test_id=test_id,
                max_tokens=512,
            )
            return self._parse_design_review_json(body["content"])
        except Exception as exc:
            logger.warning("Design review LLM failed: %s", exc)
            return {
                "verdict": "uncertain",
                "confidence": 0.0,
                "summary": f"LLM unavailable: {exc}",
                "issues": [],
            }

    def _parse_design_review_json(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return {
                "verdict": "uncertain",
                "confidence": 0.0,
                "summary": content[:300],
                "issues": [],
            }
        verdict = str(data.get("verdict", "uncertain"))
        if verdict not in DESIGN_VERDICTS:
            verdict = "uncertain"
        return {
            "verdict": verdict,
            "confidence": float(data.get("confidence", 0.0)),
            "summary": str(data.get("summary", "")),
            "issues": list(data.get("issues") or []),
        }

    def parse_bounding_box(self, content: str) -> List[int]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.replace("[", "").replace("]", "").replace(",", " ")
        parts = [int(p) for p in cleaned.split() if p.isdigit() or (p.lstrip("-").isdigit())]
        if len(parts) != 4:
            raise ValueError(f"Failed to parse bounding box from vision output: {content}")
        return parts

    def translate_normalized_box(
        self, box: List[int], viewport_width: int, viewport_height: int
    ) -> dict[str, int]:
        ymin, xmin, ymax, xmax = box
        center_x = int(((xmin + xmax) / 2 / 1000.0) * viewport_width)
        center_y = int(((ymin + ymax) / 2 / 1000.0) * viewport_height)
        return {"x": center_x, "y": center_y}


vision_analyzer = VisionAnalyzer()
