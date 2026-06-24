#!/usr/bin/env python3
"""Backfill llm_report + HTML for an existing JSON report (no browser re-run)."""
from __future__ import annotations

import argparse
import asyncio
import base64
import html as html_mod
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_screenshots_from_baselines(test_id: str, report_dir: Path) -> tuple[list[str], str | None]:
    baseline_dir = report_dir / "baselines" / test_id
    pngs = sorted(baseline_dir.glob("screenshot_*.png"))
    if not pngs:
        return [], None
    b64_list = [base64.b64encode(p.read_bytes()).decode("ascii") for p in pngs]
    return b64_list, b64_list[-1]


async def backfill(test_id: str, report_dir: Path) -> Path:
    from app.agent.report_llm import generate_llm_report
    from app.agent.report_metrics import render_report_html, write_baseline_bundle
    from app.context import TestRunContext
    from app.llm.factory import create_llm_client

    json_path = report_dir / f"{test_id}.json"
    html_path = report_dir / f"{test_id}.html"
    if not json_path.is_file():
        raise FileNotFoundError(f"Report not found: {json_path}")

    document = json.loads(json_path.read_text(encoding="utf-8"))
    ctx = TestRunContext(
        test_id=test_id,
        session_id=document.get("session_id") or f"backfill-{test_id[:8]}",
        profile=document.get("profile") or "AUTH_FLOW_MAIN",
        llm_client=create_llm_client(),
        branch="main",
    )

    _, final_b64 = _load_screenshots_from_baselines(test_id, report_dir)
    document["llm_report"] = await generate_llm_report(
        ctx,
        document,
        llm_client=ctx.llm_client,
        final_screenshot_b64=final_b64,
    )

    labels = document.get("screenshot_labels") or []
    shots, _ = _load_screenshots_from_baselines(test_id, report_dir)
    img_html = ""
    for i, shot in enumerate(shots):
        label = labels[i] if i < len(labels) else f"Screenshot {i + 1}"
        img_html += f'<h3>{html_mod.escape(label)}</h3><img src="data:image/png;base64,{shot}"/>'

    body = render_report_html(document, screenshots_html=img_html or "<p>none</p>")
    html_path.write_text(body, encoding="utf-8")
    json_path.write_text(json.dumps(document, indent=2, default=str), encoding="utf-8")
    write_baseline_bundle(test_id=test_id, document=document)
    return html_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill LLM narrative on an existing UI test report")
    parser.add_argument("test_id", help="Test UUID (e.g. de58c49e-4ecf-4859-b18b-c3813e8bfde5)")
    parser.add_argument(
        "--env-file",
        default=os.environ.get("ENV_FILE_PATH", ".env.preprod"),
        help="Env file for LiteLLM / REPORT_LLM_* settings",
    )
    args = parser.parse_args()

    env_path = Path(args.env_file)
    if not env_path.is_absolute():
        env_path = (ROOT / env_path).resolve()
    os.environ["ENV_FILE_PATH"] = str(env_path)
    sys.path.insert(0, str(ROOT))

    from app.config import settings

    report_dir = Path(settings.REPORT_DIR)
    if not report_dir.is_absolute():
        report_dir = (ROOT / report_dir).resolve()

    path = asyncio.run(backfill(args.test_id, report_dir))
    print(f"Updated report -> {path}")


if __name__ == "__main__":
    main()
