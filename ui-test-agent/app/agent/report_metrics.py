"""Build structured metrics and HTML fragments for test reports."""
from __future__ import annotations

import html
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.context import TestRunContext
from app.profiles.registry import AUTH_PROFILES
from app.profiles.modern_ui.auth_flow import auth_verification_checklist

DESIGN_FAIL_VERDICTS = frozenset({"layout_regression", "missing_content", "known_bug"})

RELEASE_DECISIONS = frozenset({"GO", "NO_GO", "GO_WITH_CAVEATS", "BASELINE_SEEDED"})


def _fmt_ms(ms: float | None) -> str:
    if ms is None:
        return "—"
    if ms >= 1000:
        return f"{ms / 1000:.2f}s"
    return f"{ms:.0f}ms"


def _safe_mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def build_environment_info(ctx: TestRunContext) -> dict[str, Any]:
    return {
        "app_env": settings.APP_ENV,
        "llm_routing": settings.llm_routing,
        "llm_planner_model": settings.LLM_PLANNER_MODEL,
        "llm_vision_model": settings.LLM_VISION_MODEL,
        "headless": settings.HEADLESS,
        "auth_login_mode": settings.AUTH_LOGIN_MODE,
        "browser_viewport": f"{settings.BROWSER_VIEWPORT_WIDTH}x{settings.BROWSER_VIEWPORT_HEIGHT}",
        "report_dir": settings.REPORT_DIR,
        "qdrant_host": settings.QDRANT_HOST,
        "qdrant_https": settings.QDRANT_HTTPS,
        "branch": ctx.branch,
        "commit_sha": ctx.commit_sha,
        "baseline_mode": ctx.baseline_mode,
        "design_review_enabled": settings.DESIGN_REVIEW_ENABLED,
        "design_gate_strict": settings.DESIGN_GATE_STRICT,
    }


def build_release_gate(
    *,
    status: str,
    results: dict[str, Any],
    design: dict[str, Any],
    timing: dict[str, Any],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Release go/no-go summary for weekly UI gate."""
    shots = design.get("screenshots") or []
    baseline_mode = (design.get("baseline_mode") or "compare").lower()
    llm_calls = sum(1 for s in shots if s.get("llm_called"))
    design_fails = [s for s in shots if s.get("verdict") in DESIGN_FAIL_VERDICTS]
    no_baseline = [s for s in shots if s.get("verdict") == "no_baseline"]
    seeded = [s for s in shots if s.get("verdict") == "seeded"]

    checklist_fail = int(results.get("checklist_fail") or 0)
    step_fail = int(timing.get("step_fail_count") or 0)
    assert_fail = int(timing.get("assert_fail_count") or 0)
    functional_ok = checklist_fail == 0 and assert_fail == 0 and not failures

    gates: list[dict[str, Any]] = []

    gates.append(
        {
            "id": "functional",
            "name": "Functional auth checklist",
            "status": "PASS" if functional_ok else "FAIL",
            "detail": (
                f"{results.get('checklist_pass', 0)}/{results.get('checklist_total', 0)} checks passed, "
                f"{len(failures)} failure(s)"
            ),
            "blocking": not functional_ok,
        }
    )

    gates.append(
        {
            "id": "playwright",
            "name": "Playwright execution",
            "status": "PASS" if step_fail == 0 else "FAIL",
            "detail": f"{timing.get('step_count', 0)} steps, {step_fail} step error(s)",
            "blocking": step_fail > 0,
        }
    )

    if design.get("skipped"):
        gates.append(
            {
                "id": "qdrant",
                "name": "Design review (Qdrant)",
                "status": "SKIP",
                "detail": str(design.get("skip_reason", "disabled")),
                "blocking": False,
            }
        )
    else:
        gates.append(
            {
                "id": "qdrant",
                "name": "Design review (Qdrant)",
                "status": "PASS",
                "detail": f"{len(shots)} screenshot(s) reviewed, mode={baseline_mode}",
                "blocking": False,
            }
        )

    if baseline_mode == "seed":
        gates.append(
            {
                "id": "baseline_compare",
                "name": "Baseline similarity",
                "status": "INFO",
                "detail": f"Seed run — {len(seeded)} baseline(s) written to Qdrant (not compared)",
                "blocking": False,
            }
        )
    elif no_baseline:
        gates.append(
            {
                "id": "baseline_compare",
                "name": "Baseline similarity",
                "status": "FAIL",
                "detail": f"{len(no_baseline)} screen(s) missing baseline — run seed first",
                "blocking": True,
            }
        )
    elif design_fails:
        gates.append(
            {
                "id": "baseline_compare",
                "name": "Baseline similarity / LLM",
                "status": "FAIL",
                "detail": f"{len(design_fails)} design regression(s) detected",
                "blocking": True,
            }
        )
    elif design.get("review_required"):
        gates.append(
            {
                "id": "baseline_compare",
                "name": "Baseline similarity / LLM",
                "status": "WARN",
                "detail": "Manual design review recommended before release",
                "blocking": settings.DESIGN_GATE_STRICT,
            }
        )
    else:
        sims = [s["similarity"] for s in shots if s.get("similarity") is not None]
        min_sim = min(sims) if sims else None
        sim_text = f"min similarity {min_sim:.2f}" if min_sim is not None else "all screens matched"
        gates.append(
            {
                "id": "baseline_compare",
                "name": "Baseline similarity",
                "status": "PASS",
                "detail": sim_text,
                "blocking": False,
            }
        )

    gates.append(
        {
            "id": "llm_vision",
            "name": "LiteLLM vision review",
            "status": "PASS" if not design_fails else "FAIL",
            "detail": f"{llm_calls} LLM call(s) on drift",
            "blocking": bool(design_fails),
        }
    )

    blockers = [g for g in gates if g.get("blocking")]
    warnings = [g for g in gates if g.get("status") in ("WARN", "INFO")]

    if status == "FAILED" or blockers:
        decision = "NO_GO"
        headline = "Do not release — blocking issue(s) detected"
        rationale = "; ".join(g["detail"] for g in blockers) or status
    elif baseline_mode == "seed":
        decision = "BASELINE_SEEDED"
        headline = "Baselines seeded — not a release compare run"
        rationale = (
            "Use baseline_mode=compare on PRs/daily; promote on main after UI merge."
        )
    elif status == "PASSED_WITH_DESIGN_DRIFT" or design.get("review_required"):
        decision = "GO_WITH_CAVEATS"
        headline = "Release with caveats — design drift or manual review needed"
        rationale = design.get("overall_verdict", "drift") or "review_required"
    elif functional_ok and design.get("auto_reviewed", False):
        decision = "GO"
        headline = "Clear for release — functional and design gates passed"
        rationale = f"Auth + design auto-reviewed ({len(shots)} screens)"
    else:
        decision = "GO_WITH_CAVEATS"
        headline = "Review recommended before release"
        rationale = "One or more gates did not fully auto-pass"

    return {
        "decision": decision,
        "headline": headline,
        "rationale": rationale,
        "test_status": status,
        "baseline_mode": baseline_mode,
        "blocking_count": len(blockers),
        "warning_count": len(warnings),
        "gates": gates,
        "blockers": [{"name": g["name"], "detail": g["detail"]} for g in blockers],
        "warnings": [{"name": g["name"], "detail": g["detail"]} for g in warnings],
        "llm_vision_calls": llm_calls,
        "screenshots_reviewed": len(shots),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_baseline_bundle(*, test_id: str, document: dict[str, Any]) -> Path | None:
    """Write manifest + release_gate.json beside baseline PNGs."""
    report_dir = Path(settings.REPORT_DIR)
    baseline_dir = report_dir / "baselines" / test_id
    if not baseline_dir.is_dir():
        return None

    pngs = sorted(baseline_dir.glob("screenshot_*.png"))
    if not pngs and not document.get("design_review", {}).get("screenshots"):
        return None

    release_gate = document.get("release_gate") or {}
    design = document.get("design_review") or {}

    screenshot_entries: list[dict[str, Any]] = []
    for shot in design.get("screenshots") or []:
        ref = shot.get("screenshot_ref") or ""
        filename = Path(ref).name if ref else None
        entry = {k: v for k, v in shot.items() if k != "screenshot_ref"}
        entry["file"] = filename
        if filename and (baseline_dir / filename).is_file():
            entry["local_path"] = str((baseline_dir / filename).resolve())
        screenshot_entries.append(entry)

    report_html = document.get("report_html") or ""
    report_json = str((report_dir / f"{test_id}.json").resolve())
    manifest = {
        "schema": "am-ui-baseline-bundle/v1",
        "test_id": test_id,
        "profile": document.get("profile"),
        "target_url": document.get("target_url"),
        "generated_at": document.get("generated_at"),
        "baseline_mode": design.get("baseline_mode") or document.get("environment", {}).get("baseline_mode"),
        "release_decision": release_gate.get("decision"),
        "release_headline": release_gate.get("headline"),
        "report_html": report_html,
        "report_json": report_json if Path(report_json).is_file() else None,
        "release_gate": release_gate,
        "llm_report": {
            "generated": (document.get("llm_report") or {}).get("generated"),
            "fallback": (document.get("llm_report") or {}).get("fallback"),
            "model": (document.get("llm_report") or {}).get("model"),
            "executive_summary": (document.get("llm_report") or {}).get("executive_summary"),
            "release_recommendation": (document.get("llm_report") or {}).get("release_recommendation"),
        },
        "design_review_summary": {
            k: design[k]
            for k in (
                "enabled",
                "skipped",
                "auto_reviewed",
                "review_required",
                "overall_verdict",
                "baseline_mode",
            )
            if k in design
        },
        "screenshots": screenshot_entries,
        "png_files": [p.name for p in pngs],
    }

    llm_report = document.get("llm_report")
    if llm_report:
        llm_path = baseline_dir / "llm_report.json"
        llm_path.write_text(json.dumps(llm_report, indent=2, default=str), encoding="utf-8")

    manifest_path = baseline_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    gate_path = baseline_dir / "release_gate.json"
    gate_path.write_text(json.dumps(release_gate, indent=2, default=str), encoding="utf-8")

    readme = baseline_dir / "README.txt"
    readme.write_text(
        "\n".join(
            [
                f"Baseline bundle for test {test_id}",
                f"Release decision: {release_gate.get('decision', '—')}",
                f"Headline: {release_gate.get('headline', '—')}",
                "",
                "Files:",
                "  manifest.json      — full metadata + design review per screenshot",
                "  release_gate.json  — go/no-go gate for release",
                "  llm_report.json    — LLM-generated release narrative (when enabled)",
                "  screenshot_*.png   — captured UI baselines",
                "",
                f"Full HTML report: {report_html or '(see parent folder)'}",
                f"Full JSON report: {report_json}",
            ]
        ),
        encoding="utf-8",
    )
    return baseline_dir


def build_timing_metrics(ctx: TestRunContext) -> dict[str, Any]:
    step_ms = [float(s["duration_ms"]) for s in ctx.step_timings if s.get("duration_ms") is not None]
    assert_pass = sum(1 for e in ctx.action_log if e.get("action") == "assert_pass")
    assert_fail = sum(1 for e in ctx.action_log if e.get("action") == "assert_fail")
    step_fail = sum(1 for e in ctx.action_log if e.get("action") == "step_failed")

    total_ms = ctx.total_duration_ms()
    slowest = max(ctx.step_timings, key=lambda s: s.get("duration_ms") or 0, default=None)

    return {
        "started_at": ctx.started_at_iso,
        "finished_at": ctx.finished_at_iso,
        "total_duration_ms": round(total_ms, 1) if total_ms is not None else None,
        "total_duration_human": _fmt_ms(total_ms),
        "step_count": len(ctx.step_timings),
        "steps_executed_ms": step_ms,
        "avg_step_ms": round(_safe_mean(step_ms), 1) if step_ms else None,
        "max_step_ms": round(max(step_ms), 1) if step_ms else None,
        "min_step_ms": round(min(step_ms), 1) if step_ms else None,
        "slowest_step": slowest,
        "assert_pass_count": assert_pass,
        "assert_fail_count": assert_fail,
        "step_fail_count": step_fail,
        "screenshot_count": sum(1 for e in ctx.action_log if e.get("action") == "screenshot"),
    }


def build_results_summary(
    *,
    status: str,
    failures: list[dict[str, Any]],
    ctx: TestRunContext,
    state: dict[str, Any],
) -> dict[str, Any]:
    checklist = []
    if ctx.profile in AUTH_PROFILES:
        checklist = auth_verification_checklist(state.get("steps") or [], ctx.action_log)

    checklist_pass = sum(1 for c in checklist if c.get("status") == "PASS")
    checklist_fail = sum(1 for c in checklist if c.get("status") == "FAIL")

    return {
        "status": status,
        "passed": status in ("PASSED", "PASSED_WITH_DESIGN_DRIFT"),
        "failure_count": len(failures),
        "failures": failures,
        "checklist": checklist,
        "checklist_pass": checklist_pass,
        "checklist_fail": checklist_fail,
        "checklist_total": len(checklist),
        "final_url": _final_url_from_log(ctx.action_log),
    }


def _final_url_from_log(action_log: list[dict[str, Any]]) -> str | None:
    for entry in reversed(action_log):
        if entry.get("action") == "assert_pass" and entry.get("url"):
            return str(entry["url"])
        if entry.get("action") == "navigate" and entry.get("url"):
            return str(entry["url"])
    return None


def _render_release_gate_html(gate: dict[str, Any]) -> str:
    decision = gate.get("decision", "—")
    colors = {
        "GO": ("#16a34a", "#ecfdf5", "#166534"),
        "NO_GO": ("#dc2626", "#fef2f2", "#991b1b"),
        "GO_WITH_CAVEATS": ("#d97706", "#fffbeb", "#92400e"),
        "BASELINE_SEEDED": ("#2563eb", "#eff6ff", "#1e40af"),
    }
    accent, bg, text = colors.get(decision, ("#6b7280", "#f9fafb", "#374151"))

    gate_rows = ""
    for g in gate.get("gates") or []:
        st = g.get("status", "")
        st_color = {
            "PASS": "#16a34a",
            "FAIL": "#dc2626",
            "WARN": "#d97706",
            "INFO": "#2563eb",
            "SKIP": "#6b7280",
        }.get(st, "#374151")
        gate_rows += (
            f"<tr>"
            f"<td>{html.escape(str(g.get('name', '')))}</td>"
            f"<td style='color:{st_color};font-weight:bold'>{html.escape(st)}</td>"
            f"<td>{html.escape(str(g.get('detail', '')))}</td>"
            f"<td>{'yes' if g.get('blocking') else '—'}</td>"
            f"</tr>"
        )

    blockers = gate.get("blockers") or []
    warnings = gate.get("warnings") or []
    blockers_html = ""
    if blockers:
        blockers_html = "<ul>" + "".join(
            f"<li><strong>{html.escape(b['name'])}:</strong> {html.escape(b['detail'])}</li>"
            for b in blockers
        ) + "</ul>"
    warnings_html = ""
    if warnings:
        warnings_html = "<ul>" + "".join(
            f"<li><strong>{html.escape(w['name'])}:</strong> {html.escape(w['detail'])}</li>"
            for w in warnings
        ) + "</ul>"

    return f"""
<section class="release-gate" style="background:{bg};border:2px solid {accent};border-radius:12px;padding:1.25rem 1.5rem;margin:1.5rem 0">
  <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap">
    <div style="font-size:2rem;font-weight:800;color:{text};letter-spacing:0.02em">{html.escape(decision)}</div>
    <div>
      <div style="font-size:1.1rem;font-weight:600;color:{text}">{html.escape(str(gate.get('headline', '')))}</div>
      <div style="color:#4b5563;margin-top:0.25rem">{html.escape(str(gate.get('rationale', '')))}</div>
    </div>
  </div>
  <p style="margin:1rem 0 0.5rem;font-size:0.85rem;color:#6b7280">
    Test status: {html.escape(str(gate.get('test_status', '')))} ·
    Baseline mode: {html.escape(str(gate.get('baseline_mode', '')))} ·
    LLM vision calls: {gate.get('llm_vision_calls', 0)} ·
    Screens reviewed: {gate.get('screenshots_reviewed', 0)}
  </p>
  <table class="data" style="margin-top:1rem">
    <tr><th>Gate</th><th>Status</th><th>Detail</th><th>Blocking</th></tr>
    {gate_rows or "<tr><td colspan=4>No gates evaluated</td></tr>"}
  </table>
  {"<h3 style='margin-top:1rem;color:#991b1b'>Blockers</h3>" + blockers_html if blockers_html else ""}
  {"<h3 style='margin-top:1rem;color:#92400e'>Warnings</h3>" + warnings_html if warnings_html else ""}
</section>
"""


def _render_llm_report_html(llm: dict[str, Any]) -> str:
    if not llm:
        return ""

    generated = llm.get("generated", False)
    fallback = llm.get("fallback", False)
    badge = "AI-generated" if generated else ("Fallback" if fallback else "Unavailable")
    badge_color = "#2563eb" if generated else "#6b7280"

    def _bullet_list(items: list[Any] | None, empty: str = "None listed.") -> str:
        if not items:
            return f"<p style='color:#6b7280'>{html.escape(empty)}</p>"
        return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items) + "</ul>"

    visual_html = ""
    if llm.get("visual_assessment"):
        visual_html = f"""
  <h3 style="margin-top:1.25rem">Visual assessment</h3>
  <p>{html.escape(str(llm['visual_assessment']))}</p>"""
    elif llm.get("visual_assessment_error"):
        visual_html = (
            f"<p style='color:#d97706;margin-top:1rem'>"
            f"Visual assessment failed: {html.escape(str(llm['visual_assessment_error']))}</p>"
        )

    model_bits: list[str] = []
    if llm.get("model"):
        model_bits.append(f"Narrative: {html.escape(str(llm['model']))}")
    if llm.get("vision_model"):
        model_bits.append(f"Vision: {html.escape(str(llm['vision_model']))}")
    model_line = " · ".join(model_bits)

    error_html = ""
    if fallback and llm.get("error"):
        error_html = (
            f"<p style='color:#92400e;font-size:0.9rem;margin-top:0.5rem'>"
            f"{html.escape(str(llm['error']))}</p>"
        )

    return f"""
<section class="llm-report" style="background:#faf5ff;border:1px solid #c4b5fd;border-radius:12px;padding:1.25rem 1.5rem;margin:1.5rem 0">
  <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;margin-bottom:0.75rem">
    <h2 style="margin:0;border:none;padding:0">Release narrative (LLM)</h2>
    <span style="background:{badge_color};color:#fff;font-size:0.75rem;font-weight:600;padding:0.2rem 0.6rem;border-radius:999px">{html.escape(badge)}</span>
  </div>
  {f"<p style='font-size:0.85rem;color:#6b7280;margin:0 0 1rem'>{model_line}</p>" if model_line else ""}
  {error_html}
  <h3 style="margin-top:0">Executive summary</h3>
  <p>{html.escape(str(llm.get("executive_summary") or ""))}</p>
  <h3>Release recommendation</h3>
  <p style="font-weight:600">{html.escape(str(llm.get("release_recommendation") or ""))}</p>
  <h3>Risks</h3>
  {_bullet_list(llm.get("risks") if isinstance(llm.get("risks"), list) else None)}
  <h3>Next steps</h3>
  {_bullet_list(llm.get("next_steps") if isinstance(llm.get("next_steps"), list) else None)}
  <h3>Stakeholder note</h3>
  <p>{html.escape(str(llm.get("stakeholder_note") or ""))}</p>{visual_html}
</section>
"""


def _render_design_review_html(design: dict[str, Any]) -> str:
    if not design or design.get("skipped"):
        reason = html.escape(str(design.get("skip_reason", "disabled")))
        return f"<p>Design review skipped ({reason}).</p>"

    overall = html.escape(str(design.get("overall_verdict", "")))
    review_required = design.get("review_required", False)
    auto = design.get("auto_reviewed", False)
    badge_color = "#16a34a" if not review_required else "#d97706"

    rows = ""
    for shot in design.get("screenshots") or []:
        verdict = html.escape(str(shot.get("verdict", "")))
        sim = shot.get("similarity")
        sim_text = f"{sim:.2f}" if sim is not None else "—"
        file_name = html.escape(str(shot.get("file") or Path(str(shot.get("screenshot_ref", ""))).name or "—"))
        rows += (
            f"<tr>"
            f"<td>{html.escape(str(shot.get('step_label', '')))}</td>"
            f"<td>{html.escape(str(shot.get('route', '')))}</td>"
            f"<td>{file_name}</td>"
            f"<td>{sim_text}</td>"
            f"<td>{verdict}</td>"
            f"<td>{'yes' if shot.get('llm_called') else 'no'}</td>"
            f"<td>{html.escape(str(shot.get('llm_summary', '')))}</td>"
            f"</tr>"
        )

    return f"""
<div class="result-box" style="border-color:{badge_color}">
  <strong>Overall verdict:</strong> {overall}<br/>
  <strong>Baseline mode:</strong> {html.escape(str(design.get('baseline_mode', '')))}<br/>
  <strong>Auto-reviewed:</strong> {auto}<br/>
  <strong>Review required:</strong> {review_required}
</div>
<table class="data">
  <tr><th>Step</th><th>Route</th><th>Baseline file</th><th>Similarity</th><th>Verdict</th><th>LLM</th><th>Summary</th></tr>
  {rows or "<tr><td colspan=7>No screenshots reviewed</td></tr>"}
</table>
<p style="color:#6b7280;font-size:0.9rem">Baseline PNGs + manifest.json live under <code>baselines/&lt;test_id&gt;/</code></p>
"""


def build_report_document(
    *,
    ctx: TestRunContext,
    state: dict[str, Any],
    status: str,
    report_path: str,
) -> dict[str, Any]:
    failures = state.get("failures_encountered") or []
    finished_at = datetime.now(timezone.utc).isoformat()
    ctx.finished_at_iso = finished_at

    environment = build_environment_info(ctx)
    timing = build_timing_metrics(ctx)
    results = build_results_summary(status=status, failures=failures, ctx=ctx, state=state)
    design_review = state.get("design_review_summary") or {}
    release_gate = build_release_gate(
        status=status,
        results=results,
        design=design_review,
        timing=timing,
        failures=failures,
    )

    return {
        "schema": "am-ui-test-report/v2",
        "test_id": ctx.test_id,
        "session_id": ctx.session_id,
        "profile": ctx.profile,
        "target_url": state.get("target_url"),
        "status": status,
        "generated_at": finished_at,
        "report_html": report_path,
        "release_gate": release_gate,
        "environment": environment,
        "timing": timing,
        "results": results,
        "design_review": design_review,
        "visual_anomalies": state.get("visual_anomalies") or [],
        "planned_steps": state.get("steps") or [],
        "action_log": ctx.action_log,
        "step_timings": ctx.step_timings,
        "screenshot_labels": state.get("screenshot_labels") or [],
        "screenshot_count": len(state.get("screenshot_history") or []),
        "baseline_bundle_dir": str(
            (Path(settings.REPORT_DIR) / "baselines" / ctx.test_id).resolve()
        ),
    }


def render_report_html(document: dict[str, Any], *, screenshots_html: str) -> str:
    status = document["status"]
    passed = status in ("PASSED", "PASSED_WITH_DESIGN_DRIFT")
    timing = document["timing"]
    results = document["results"]
    env = document["environment"]
    failures = results["failures"]
    checklist = results["checklist"]
    design = document.get("design_review") or {}
    release_gate = document.get("release_gate") or {}
    llm_report = document.get("llm_report") or {}
    baseline_dir = document.get("baseline_bundle_dir") or ""

    if status == "FAILED":
        status_color = "#dc2626"
    elif status == "PASSED_WITH_DESIGN_DRIFT":
        status_color = "#d97706"
    else:
        status_color = "#16a34a"

    metrics_cards = f"""
    <div class="metrics">
      <div class="card"><div class="label">Total time</div><div class="value">{html.escape(timing.get("total_duration_human") or "—")}</div></div>
      <div class="card"><div class="label">Steps</div><div class="value">{timing.get("step_count", 0)}</div></div>
      <div class="card"><div class="label">Avg step</div><div class="value">{_fmt_ms(timing.get("avg_step_ms"))}</div></div>
      <div class="card"><div class="label">Slowest step</div><div class="value">{_fmt_ms((timing.get("slowest_step") or {}).get("duration_ms"))}</div></div>
      <div class="card"><div class="label">Assertions</div><div class="value">{timing.get("assert_pass_count", 0)} pass / {timing.get("assert_fail_count", 0)} fail</div></div>
      <div class="card"><div class="label">Screenshots</div><div class="value">{document.get("screenshot_count", 0)}</div></div>
    </div>
    """

    slowest = timing.get("slowest_step") or {}
    slowest_label = html.escape(str(slowest.get("name") or slowest.get("action") or "—"))

    env_rows = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in env.items()
    )

    timeline_rows = ""
    cumulative = 0.0
    for row in document.get("step_timings") or []:
        dur = float(row.get("duration_ms") or 0)
        cumulative += dur
        st = row.get("status", "ok")
        color = "#16a34a" if st == "ok" else "#dc2626"
        timeline_rows += (
            f"<tr>"
            f"<td>{row.get('index', '')}</td>"
            f"<td>{html.escape(str(row.get('name', '')))}</td>"
            f"<td>{html.escape(str(row.get('action', '')))}</td>"
            f"<td>{html.escape(str(row.get('phase', '')))}</td>"
            f"<td>{_fmt_ms(dur)}</td>"
            f"<td>{_fmt_ms(cumulative)}</td>"
            f"<td style='color:{color};font-weight:bold'>{html.escape(st)}</td>"
            f"</tr>"
        )

    action_rows = ""
    for entry in document.get("action_log") or []:
        dur = entry.get("duration_ms")
        extras = {k: v for k, v in entry.items() if k not in ("action", "step", "name", "ts", "duration_ms")}
        action_rows += (
            f"<tr>"
            f"<td>{html.escape(str(entry.get('ts', '')))}</td>"
            f"<td>{html.escape(str(entry.get('action', '')))}</td>"
            f"<td>{html.escape(str(entry.get('step', entry.get('name', ''))))}</td>"
            f"<td>{_fmt_ms(float(dur)) if dur is not None else '—'}</td>"
            f"<td><code>{html.escape(json.dumps(extras, default=str))}</code></td>"
            f"</tr>"
        )

    checklist_html = ""
    for item in checklist:
        color = {"PASS": "#16a34a", "FAIL": "#dc2626", "SKIP": "#6b7280"}.get(item["status"], "#2563eb")
        checklist_html += (
            f"<tr><td>{html.escape(item['name'])}</td>"
            f"<td style='color:{color};font-weight:bold'>{item['status']}</td></tr>"
        )

    failures_html = ""
    for failure in failures:
        failures_html += f"<li><pre>{html.escape(json.dumps(failure, indent=2, default=str))}</pre></li>"

    steps_html = ""
    for step in document.get("planned_steps") or []:
        label = html.escape(step.get("name") or str(step))
        steps_html += f"<li>{label}<br/><code>{html.escape(str(step))}</code></li>"

    result_summary = f"""
    <div class="result-box" style="border-color:{status_color}">
      <strong>Result:</strong> {status}<br/>
      <strong>Failures:</strong> {results.get('failure_count', 0)}<br/>
      <strong>Auth checklist:</strong> {results.get('checklist_pass', 0)}/{results.get('checklist_total', 0)} passed<br/>
      <strong>Final URL:</strong> {html.escape(results.get('final_url') or '—')}<br/>
      <strong>Started:</strong> {html.escape(timing.get('started_at') or '—')}<br/>
      <strong>Finished:</strong> {html.escape(timing.get('finished_at') or '—')}<br/>
      <strong>Slowest:</strong> {slowest_label} ({_fmt_ms(slowest.get('duration_ms'))})
    </div>
    """

    auth_section = ""
    if checklist:
        auth_section = f"""
<h2>Authentication verification checklist</h2>
<table class="data">
<tr><th>Check</th><th>Status</th></tr>
{checklist_html or "<tr><td colspan=2>No checks</td></tr>"}
</table>
"""

    login_label = "Demo Login" if settings.AUTH_LOGIN_MODE == "demo" else settings.TEST_USER_EMAIL
    design_section = f"""
<h2>Design review (Hybrid Qdrant + LLM)</h2>
{_render_design_review_html(design)}
"""

    baseline_note = ""
    if baseline_dir:
        baseline_note = f"""
<p style="background:#f3f4f6;padding:0.75rem;border-radius:6px">
  <strong>Baseline bundle:</strong> <code>{html.escape(baseline_dir)}</code>
  — contains <code>manifest.json</code>, <code>release_gate.json</code>, <code>llm_report.json</code>, and <code>screenshot_*.png</code>
</p>
"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>AM UI Release Report — {html.escape(release_gate.get('decision', status))}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 1200px; color: #111; }}
    h1 {{ color: {status_color}; margin-bottom: 0.5rem; }}
    h2 {{ margin-top: 2rem; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.25rem; }}
    .meta, .result-box {{ background: #f9fafb; padding: 1rem; border-radius: 8px; margin: 1rem 0; }}
    .result-box {{ border-left: 4px solid; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; margin: 1rem 0; }}
    .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 0.75rem; }}
    .card .label {{ font-size: 0.75rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em; }}
    .card .value {{ font-size: 1.25rem; font-weight: 600; margin-top: 0.25rem; }}
    table.data {{ width: 100%; border-collapse: collapse; margin: 0.5rem 0 1rem; }}
    table.data th, table.data td {{ border: 1px solid #e5e7eb; padding: 8px; text-align: left; vertical-align: top; }}
    table.data th {{ background: #f3f4f6; }}
    code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; word-break: break-all; }}
    img {{ max-width: 100%; border: 1px solid #ccc; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>AM UI Release Report</h1>
  <p style="color:#6b7280;margin-top:0">Profile: {html.escape(document.get('profile', ''))} · Target: {html.escape(document.get('target_url') or '')} · Test status: {status}</p>

  {_render_release_gate_html(release_gate)}
  {_render_llm_report_html(llm_report)}
  {baseline_note}

  {result_summary}
  {metrics_cards}

  <div class="meta">
    <strong>Test ID:</strong> {html.escape(document.get('test_id', ''))}<br/>
    <strong>Session:</strong> {html.escape(document.get('session_id', ''))}<br/>
    <strong>Login mode:</strong> {html.escape(login_label)}<br/>
    <strong>Report file:</strong> {html.escape(document.get('report_html', ''))}
  </div>

  <h2>Environment</h2>
  <table class="data"><tr><th>Key</th><th>Value</th></tr>{env_rows}</table>

  <h2>Step timeline (latency)</h2>
  <table class="data">
    <tr><th>#</th><th>Step</th><th>Action</th><th>Phase</th><th>Duration</th><th>Cumulative</th><th>Status</th></tr>
    {timeline_rows or "<tr><td colspan=7>No step timings recorded</td></tr>"}
  </table>

  {auth_section}

  {design_section}

  <h2>Execution log</h2>
  <table class="data">
    <tr><th>Time (UTC)</th><th>Action</th><th>Step</th><th>Duration</th><th>Details</th></tr>
    {action_rows or "<tr><td colspan=5>No actions logged</td></tr>"}
  </table>

  <h2>Planned steps</h2>
  <ol>{steps_html or "<li>none</li>"}</ol>

  <h2>Failures</h2>
  <ul>{failures_html or "<li>none</li>"}</ul>

  <h2>Screenshots</h2>
  {screenshots_html or "<p>none</p>"}
</body>
</html>"""
