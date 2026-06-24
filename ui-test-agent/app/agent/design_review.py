"""Hybrid design review — Qdrant ui_patterns similarity + vision LLM on drift."""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from langchain_core.runnables import RunnableConfig

from app.agent.design_status import compute_final_status
from app.agent.state import AutonomousAgentState
from app.config import settings
from app.context import get_test_context
from app.memory.embedder import decode_image_bytes, embed_image
from app.memory.qdrant import qdrant_memory
from app.profiles.registry import AUTH_PROFILES
from app.profiles.modern_ui.auth_flow import auth_verification_checklist
from app.vision.analyzer import vision_analyzer

logger = logging.getLogger(__name__)

FAIL_VERDICTS = frozenset({"layout_regression", "missing_content", "known_bug"})


def _skipped_summary(reason: str) -> dict[str, Any]:
    return {
        "enabled": settings.DESIGN_REVIEW_ENABLED,
        "skipped": True,
        "skip_reason": reason,
        "auto_reviewed": True,
        "review_required": False,
        "overall_verdict": "pass",
        "baseline_mode": settings.BASELINE_MODE,
        "screenshots": [],
    }


def infer_route_from_url(url: str) -> str:
    parsed = urlparse(url)
    fragment = (parsed.fragment or "").strip("/")
    if fragment:
        return "/" + fragment.split("?")[0]
    path = parsed.path.strip("/")
    return f"/{path}" if path else "/"


def _resolve_route(state: AutonomousAgentState, ctx, index: int) -> str:
    visited = state.get("visited_routes") or []
    if index < len(visited) and visited[index]:
        return visited[index]
    for entry in reversed(ctx.action_log):
        if entry.get("action") == "assert_pass" and entry.get("url"):
            return infer_route_from_url(str(entry["url"]))
    target = state.get("target_url") or ""
    return infer_route_from_url(target) if target else "/"


def _functional_checklist(state: AutonomousAgentState, ctx) -> list[str]:
    if ctx.profile in AUTH_PROFILES:
        items = auth_verification_checklist(state.get("steps") or [], ctx.action_log)
        return [c["name"] for c in items if c.get("status") == "PASS"]
    return []


def _save_screenshot_file(test_id: str, index: int, screenshot_b64: str) -> str:
    report_dir = Path(settings.REPORT_DIR)
    dest_dir = report_dir / "baselines" / test_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"screenshot_{index + 1}.png"
    dest.write_bytes(decode_image_bytes(screenshot_b64))
    return str(dest.resolve())


def _load_baseline_b64(screenshot_ref: str | None) -> str | None:
    if not screenshot_ref:
        return None
    path = Path(screenshot_ref)
    if not path.is_file():
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _aggregate_verdict(results: list[dict[str, Any]]) -> str:
    if any(r.get("verdict") in FAIL_VERDICTS for r in results):
        return "fail"
    if any(r.get("verdict") == "uncertain" for r in results):
        return "uncertain"
    if any(r.get("verdict") == "intentional_redesign" for r in results):
        return "drift"
    return "pass"


async def design_review_node(
    state: AutonomousAgentState, config: RunnableConfig
) -> dict[str, Any]:
    ctx = get_test_context(config)
    baseline_mode = (
        state.get("baseline_mode") or ctx.baseline_mode or settings.BASELINE_MODE
    ).lower()

    if not settings.DESIGN_REVIEW_ENABLED:
        summary = _skipped_summary("DESIGN_REVIEW_ENABLED=false")
        return {"design_review_summary": summary, "design_review_results": []}

    if not qdrant_memory.available:
        summary = _skipped_summary("qdrant_unavailable")
        ctx.log_action("design_review_skipped", reason="qdrant_unavailable")
        return {"design_review_summary": summary, "design_review_results": []}

    screenshots = state.get("screenshot_history") or []
    labels = state.get("screenshot_labels") or []
    if not screenshots:
        summary = _skipped_summary("no_screenshots")
        return {"design_review_summary": summary, "design_review_results": []}

    checklist = _functional_checklist(state, ctx)
    results: list[dict[str, Any]] = []
    anomalies: list[str] = []
    failures = list(state.get("failures_encountered") or [])

    for idx, shot in enumerate(screenshots):
        label = labels[idx] if idx < len(labels) else f"Screenshot {idx + 1}"
        route = _resolve_route(state, ctx, idx)
        screenshot_ref = _save_screenshot_file(ctx.test_id, idx, shot)
        vector = await embed_image(shot)

        bug_hits = qdrant_memory.search_bug_memory(vector, limit=1)
        if bug_hits and bug_hits[0]["score"] >= settings.DESIGN_BUG_MEMORY_THRESHOLD:
            verdict = "known_bug"
            row = {
                "step_label": label,
                "route": route,
                "similarity": round(bug_hits[0]["score"], 4),
                "verdict": verdict,
                "llm_summary": "Matches known bug pattern in bug_memory.",
                "llm_called": False,
                "baseline_design_version": None,
                "screenshot_ref": screenshot_ref,
                "promoted": False,
            }
            results.append(row)
            anomalies.append(f"{label}: known bug pattern (score={bug_hits[0]['score']:.2f})")
            failures.append(
                {
                    "type": "design_regression",
                    "step_label": label,
                    "verdict": verdict,
                    "error": row["llm_summary"],
                }
            )
            continue

        hits = qdrant_memory.search_ui_pattern(
            profile=ctx.profile,
            route=route,
            step_label=label,
            vector=vector,
            limit=1,
        )
        similarity = float(hits[0]["score"]) if hits else None
        baseline_payload = hits[0]["payload"] if hits else {}
        baseline_version = baseline_payload.get("design_version")
        baseline_b64 = _load_baseline_b64(baseline_payload.get("screenshot_ref"))

        row: dict[str, Any] = {
            "step_label": label,
            "route": route,
            "similarity": round(similarity, 4) if similarity is not None else None,
            "verdict": "matches_baseline",
            "llm_summary": "",
            "llm_called": False,
            "baseline_design_version": baseline_version,
            "screenshot_ref": screenshot_ref,
            "promoted": False,
        }

        if not hits and baseline_mode == "seed":
            upsert = qdrant_memory.upsert_ui_pattern(
                profile=ctx.profile,
                route=route,
                step_label=label,
                vector=vector,
                screenshot_ref=screenshot_ref,
                commit_sha=ctx.commit_sha,
                test_id=ctx.test_id,
            )
            row["verdict"] = "seeded"
            row["llm_summary"] = f"Initial baseline seeded (v{upsert.get('design_version', '?')})."
            row["baseline_design_version"] = upsert.get("design_version")
            row["promoted"] = True
            results.append(row)
            continue

        if not hits:
            row["verdict"] = "no_baseline"
            row["llm_summary"] = "No active baseline — run with baseline_mode=seed first."
            row["review_required"] = True
            results.append(row)
            continue

        if similarity is not None and similarity >= settings.DESIGN_SIMILARITY_PASS:
            row["llm_summary"] = f"Auto-pass: similarity {similarity:.2f} >= {settings.DESIGN_SIMILARITY_PASS}."
            if baseline_mode == "promote":
                upsert = qdrant_memory.upsert_ui_pattern(
                    profile=ctx.profile,
                    route=route,
                    step_label=label,
                    vector=vector,
                    screenshot_ref=screenshot_ref,
                    commit_sha=ctx.commit_sha,
                    test_id=ctx.test_id,
                )
                row["promoted"] = True
                row["baseline_design_version"] = upsert.get("design_version")
                row["llm_summary"] += f" Baseline refreshed to v{upsert.get('design_version', '?')}."
            results.append(row)
            continue

        needs_llm = (
            settings.LLM_VISION_ENABLED
            and (
                similarity is None
                or similarity < settings.DESIGN_SIMILARITY_REVIEW
                or baseline_mode == "promote"
            )
        )
        if baseline_mode == "seed" and (
            similarity is None or similarity < settings.DESIGN_SIMILARITY_PASS
        ):
            upsert = qdrant_memory.upsert_ui_pattern(
                profile=ctx.profile,
                route=route,
                step_label=label,
                vector=vector,
                screenshot_ref=screenshot_ref,
                commit_sha=ctx.commit_sha,
                test_id=ctx.test_id,
            )
            row["verdict"] = "seeded"
            row["llm_summary"] = (
                "Baseline seeded for step (similarity "
                f"{similarity:.2f})."
                if similarity is not None
                else "Baseline seeded for step."
            )
            row["baseline_design_version"] = upsert.get("design_version")
            row["promoted"] = True
            results.append(row)
            continue

        if needs_llm:
            review = await vision_analyzer.review_design_change(
                current_b64=shot,
                baseline_b64=baseline_b64,
                checklist=checklist,
                step_label=label,
                llm_client=ctx.llm_client,
                session_id=ctx.session_id,
                test_id=ctx.test_id,
            )
            row["verdict"] = review["verdict"]
            row["llm_summary"] = review.get("summary", "")
            row["llm_called"] = True
            row["confidence"] = review.get("confidence")
            if review.get("issues"):
                row["issues"] = review["issues"]

            if review["verdict"] in FAIL_VERDICTS:
                anomalies.append(f"{label}: {review['verdict']} — {review.get('summary', '')}")
                failures.append(
                    {
                        "type": "design_regression",
                        "step_label": label,
                        "verdict": review["verdict"],
                        "error": review.get("summary", ""),
                    }
                )
            elif review["verdict"] == "intentional_redesign" and baseline_mode == "promote":
                upsert = qdrant_memory.upsert_ui_pattern(
                    profile=ctx.profile,
                    route=route,
                    step_label=label,
                    vector=vector,
                    screenshot_ref=screenshot_ref,
                    commit_sha=ctx.commit_sha,
                    test_id=ctx.test_id,
                )
                row["promoted"] = True
                row["baseline_design_version"] = upsert.get("design_version")
                row["llm_summary"] = (
                    f"{review.get('summary', '')} Baseline promoted to v{upsert.get('design_version', '?')}."
                )
            elif review["verdict"] == "intentional_redesign":
                anomalies.append(f"{label}: intentional redesign detected — run promote on main.")
        else:
            row["llm_summary"] = (
                f"Gray zone similarity {similarity:.2f}; treated as pass without LLM."
            )

        results.append(row)

    overall = _aggregate_verdict(results)
    review_required = overall in ("uncertain", "drift") or any(
        r.get("verdict") in ("no_baseline", "uncertain") for r in results
    )
    auto_reviewed = not review_required and overall == "pass"

    summary = {
        "enabled": True,
        "skipped": False,
        "auto_reviewed": auto_reviewed,
        "review_required": review_required,
        "overall_verdict": overall,
        "baseline_mode": baseline_mode,
        "screenshots": results,
    }

    ctx.log_action(
        "design_review",
        overall_verdict=overall,
        review_required=review_required,
        screenshot_count=len(results),
    )

    return {
        "design_review_results": results,
        "design_review_summary": summary,
        "visual_anomalies": list(state.get("visual_anomalies") or []) + anomalies,
        "failures_encountered": failures,
    }


def merge_design_failures(state: dict[str, Any]) -> None:
    """Ensure design failures are reflected before status computation."""
    compute_final_status(state)
