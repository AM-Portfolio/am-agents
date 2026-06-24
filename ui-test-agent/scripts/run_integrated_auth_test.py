#!/usr/bin/env python3
"""
Run auth flow end-to-end in-process: Playwright → Qdrant design review → LiteLLM → HTML report.

No ui-test-agent HTTP server required. Uses .env.preprod by default.

Usage:
  python scripts/run_integrated_auth_test.py
  python scripts/run_integrated_auth_test.py --baseline-mode seed --open-report
  python scripts/run_integrated_auth_test.py --target-file ../../am-modern-ui/testing/targets.preprod.json --target main
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _resolve_target(args: argparse.Namespace) -> tuple[str, str, str]:
    target_url = args.url
    ui_mode = args.mode
    profile = None

    target_file = args.target_file
    if target_file:
        from app.target_loader import get_target_config

        tf = (ROOT / target_file).resolve() if not Path(target_file).is_absolute() else Path(target_file)
        env_file = Path(args.env_file).resolve() if args.env_file else None
        if env_file is None:
            env_name = tf.stem.replace("targets.", "")
            for candidate in (
                tf.parent.parent / f".env.{env_name}",
                ROOT.parent / "am-modern-ui" / f".env.{env_name}",
            ):
                if candidate.is_file():
                    env_file = candidate
                    break
        cfg = get_target_config(tf, target_name=args.target or args.mode, env_file=env_file)
        target_url = target_url or cfg.base_url
        ui_mode = ui_mode or cfg.ui_mode
        profile = cfg.profile

    ui_mode = (ui_mode or os.environ.get("UI_APP_MODE") or "main").lower()
    if not target_url:
        from app.config import settings

        target_url = (
            settings.MODERN_UI_MAIN_URL if ui_mode == "main" else settings.MODERN_UI_PORTFOLIO_URL
        )
    if not profile:
        profile = "AUTH_FLOW_MAIN" if ui_mode == "main" else "AUTH_FLOW_PORTFOLIO"
    return target_url, ui_mode, profile


async def _run(args: argparse.Namespace) -> int:
    target_url, ui_mode, profile = _resolve_target(args)

    from app.config import settings
    from app.runner import execute_ui_test

    test_id = str(uuid.uuid4())
    payload = {
        "targetUrl": target_url,
        "specification": "",
        "profile": profile,
        "commitSha": args.commit_sha,
        "branch": args.branch,
        "baselineMode": args.baseline_mode or settings.BASELINE_MODE,
    }

    if not args.json:
        print("=== Integrated UI test (Playwright + Qdrant + LiteLLM) ===")
        print(f"  test_id     = {test_id}")
        print(f"  target      = {target_url}")
        print(f"  profile     = {profile}")
        print(f"  qdrant      = {'https' if settings.QDRANT_HTTPS else 'http'}://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
        print(f"  litellm     = {settings.LITELLM_BASE_URL} ({settings.LLM_ROUTING})")
        print(f"  design      = {settings.DESIGN_REVIEW_ENABLED} baseline={payload['baselineMode']}")
        print(f"  report_dir  = {settings.REPORT_DIR}")
        print()

    result = await execute_ui_test(test_id, payload)
    report = result.get("report")
    design = result.get("design_review") or {}

    if args.json:
        print(json.dumps({**result, "targetUrl": target_url, "uiMode": ui_mode}, indent=2, default=str))
    else:
        print(f"Status: {result.get('status')}")
        if design and not design.get("skipped"):
            print(
                f"Design review: verdict={design.get('overall_verdict')} "
                f"screenshots={len(design.get('screenshots') or [])} "
                f"llm_calls={sum(1 for s in (design.get('screenshots') or []) if s.get('llm_called'))}"
            )
        if report:
            print(f"Report HTML: {report}")
            print(f"Report JSON: {Path(report).with_suffix('.json')}")
        if result.get("error"):
            print(f"Error: {result['error']}", file=sys.stderr)

    if args.open_report and report and Path(report).is_file():
        webbrowser.open(Path(report).resolve().as_uri())

    if result.get("status") == "COMPLETED":
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run auth UI test with Playwright, Qdrant baselines, and LiteLLM design review"
    )
    parser.add_argument(
        "--env-file",
        default=os.environ.get("ENV_FILE_PATH", ".env.preprod"),
        help="Env file (Qdrant, LiteLLM, design review)",
    )
    parser.add_argument("--url", default=None, help="Target UI base URL")
    parser.add_argument("--mode", choices=["portfolio", "main"], default=None)
    parser.add_argument("--target-file", default="../../am-modern-ui/testing/targets.preprod.json")
    parser.add_argument("--target", default="main")
    parser.add_argument("--env-file-target", dest="env_file", default=None)
    parser.add_argument(
        "--baseline-mode",
        choices=["compare", "seed", "promote"],
        default=None,
        help="Qdrant baseline: seed (first run), compare (PR), promote (after UI merge)",
    )
    parser.add_argument("--branch", default="main")
    parser.add_argument("--commit-sha", default=None)
    parser.add_argument("--open-report", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    env_path = Path(args.env_file)
    if not env_path.is_absolute():
        env_path = (ROOT / env_path).resolve()
    os.environ["ENV_FILE_PATH"] = str(env_path)
    sys.path.insert(0, str(ROOT))

    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
