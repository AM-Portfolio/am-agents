"""Promote design baselines from a completed test report."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.memory.embedder import embed_image_bytes
from app.memory.qdrant import qdrant_memory

logger = logging.getLogger(__name__)

router = APIRouter()


class PromoteBaselineRequest(BaseModel):
    testId: str = Field(..., description="Completed test ID with report JSON on disk")
    stepLabels: Optional[list[str]] = Field(
        default=None,
        description="Optional subset of screenshot step labels to promote",
    )
    profile: Optional[str] = Field(default=None, description="Override profile from report")


class PromoteBaselineResponse(BaseModel):
    testId: str
    promoted: list[dict[str, Any]]
    message: str


def _load_report_json(test_id: str) -> dict[str, Any]:
    path = Path(settings.REPORT_DIR) / f"{test_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Report JSON not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/baseline/promote", response_model=PromoteBaselineResponse)
async def promote_design_baseline(request: PromoteBaselineRequest):
    if not qdrant_memory.available:
        raise HTTPException(status_code=503, detail="Qdrant unavailable")

    document = _load_report_json(request.testId)
    profile = request.profile or document.get("profile") or "AUTH_FLOW_MAIN"
    design = document.get("design_review") or {}
    screenshots = design.get("screenshots") or []

    if not screenshots:
        raise HTTPException(
            status_code=400,
            detail="Report has no design_review.screenshots — run test with design review enabled",
        )

    labels_filter = set(request.stepLabels) if request.stepLabels else None
    promoted: list[dict[str, Any]] = []

    for shot in screenshots:
        label = shot.get("step_label") or ""
        if labels_filter and label not in labels_filter:
            continue
        screenshot_ref = shot.get("screenshot_ref")
        if not screenshot_ref:
            continue
        path = Path(screenshot_ref)
        if not path.is_file():
            logger.warning("Screenshot file missing for promote: %s", path)
            continue
        vector = await embed_image_bytes(path.read_bytes())
        route = shot.get("route") or "/"
        upsert = qdrant_memory.upsert_ui_pattern(
            profile=profile,
            route=route,
            step_label=label,
            vector=vector,
            screenshot_ref=str(path.resolve()),
            commit_sha=document.get("environment", {}).get("commit_sha"),
            test_id=request.testId,
        )
        if upsert:
            promoted.append(
                {
                    "step_label": label,
                    "route": route,
                    "design_version": upsert.get("design_version"),
                    "point_id": upsert.get("point_id"),
                }
            )

    if not promoted:
        raise HTTPException(status_code=400, detail="No baselines promoted — check stepLabels and screenshot files")

    return PromoteBaselineResponse(
        testId=request.testId,
        promoted=promoted,
        message=f"Promoted {len(promoted)} baseline(s) for profile {profile}",
    )
