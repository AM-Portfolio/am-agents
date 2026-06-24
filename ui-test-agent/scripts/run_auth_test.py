#!/usr/bin/env python3
"""
Run authentication flow test via ui-test-agent.

Usage:
  python scripts/run_auth_test.py
  python scripts/run_auth_test.py --target-file ../../am-modern-ui/testing/targets.preprod.json --target main
  python scripts/run_auth_test.py --url http://localhost:9000 --mode main
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def _open_report(report: str | None, test_id: str, base: str) -> None:
    if report:
        path = Path(report)
        if path.is_file():
            webbrowser.open(path.resolve().as_uri())
            return
    webbrowser.open(f"{base}/api/v1/test/report/{test_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run UI auth flow via ui-test-agent")
    parser.add_argument("--agent-url", default="http://localhost:8130", help="ui-test-agent base URL")
    parser.add_argument("--url", default=None, help="Target UI URL (overrides target file)")
    parser.add_argument("--mode", choices=["portfolio", "main"], default=None, help="Target key / uiMode")
    parser.add_argument(
        "--target-file",
        default=None,
        help="Wrapper targets JSON (e.g. am-modern-ui/testing/targets.preprod.json)",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Named target inside --target-file (default: default_target from file)",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Env file for ${VAR} substitution in target file (default: sibling .env.<env>)",
    )
    parser.add_argument("--timeout", type=int, default=180, help="Max wait seconds")
    parser.add_argument("--open-report", action="store_true", help="Open HTML report when done")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON result (for MCP tools)")
    parser.add_argument(
        "--baseline-mode",
        choices=["compare", "seed", "promote"],
        default=None,
        help="Qdrant baseline lifecycle: compare (default), seed, promote",
    )
    args = parser.parse_args()

    target_file = args.target_file or __import__("os").environ.get("TARGET_FILE")
    ui_mode = args.mode
    target_url = args.url

    if target_file:
        from app.target_loader import get_target_config, load_env_file

        tf = Path(target_file).resolve()
        env_file = Path(args.env_file).resolve() if args.env_file else None
        if env_file is None:
            env_name = tf.stem.replace("targets.", "")
            candidate = tf.parent.parent / f".env.{env_name}"
            if candidate.is_file():
                env_file = candidate
        cfg = get_target_config(tf, target_name=args.target or args.mode, env_file=env_file)
        if not target_url:
            target_url = cfg.base_url
        if not ui_mode:
            ui_mode = cfg.ui_mode
        print(f"Target file: {tf}", flush=True)
        print(f"  module={cfg.module} env={cfg.environment} profile={cfg.profile}", flush=True)

    if not ui_mode:
        ui_mode = "portfolio"

    payload: dict = {"uiMode": ui_mode}
    if target_url:
        payload["targetUrl"] = target_url
    if args.baseline_mode:
        payload["baselineMode"] = args.baseline_mode

    base = args.agent_url.rstrip("/")

    def emit_result(payload: dict, exit_code: int) -> int:
        if args.json:
            print(json.dumps(payload, indent=2))
        return exit_code

    if not args.json:
        print(f"POST {base}/api/v1/test/run/auth", flush=True)
        print(f"  mode={ui_mode} url={target_url or '(agent default)'}", flush=True)

    with httpx.Client(timeout=30.0) as client:
        try:
            resp = client.post(f"{base}/api/v1/test/run/auth", json=payload)
            resp.raise_for_status()
        except httpx.ConnectError:
            print("ERROR: Cannot connect to ui-test-agent. Start it first (separate terminal):", file=sys.stderr)
            print("  cd am-ui-test-agent && npm run preprod", file=sys.stderr)
            return 1

        body = resp.json()
        test_id = body["testId"]
        if not args.json:
            print(f"Queued test_id={test_id}", flush=True)

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            status_resp = client.get(f"{base}/api/v1/test/status/{test_id}")
            status_resp.raise_for_status()
            data = status_resp.json()
            status = data.get("status", "UNKNOWN")
            if not args.json:
                print(f"  status={status}", flush=True)
            if status == "COMPLETED":
                report = data.get("report")
                report_path = Path(report).resolve() if report else None
                result = {
                    "testId": test_id,
                    "status": status,
                    "targetUrl": target_url,
                    "uiMode": ui_mode,
                    "report": str(report_path) if report_path else report,
                    "reportUrl": f"{base}/api/v1/test/report/{test_id}",
                }
                if not args.json:
                    print("\n=== PASSED ===", flush=True)
                    if report_path and report_path.is_file():
                        print(f"Report file: {report_path}", flush=True)
                        print(f"Report folder: {report_path.parent}", flush=True)
                    elif report:
                        print(f"Report: {report}", flush=True)
                    print(f"View in browser: {base}/api/v1/test/report/{test_id}", flush=True)
                if args.open_report:
                    _open_report(report, test_id, base)
                return emit_result(result, 0)
            if status == "FAILED":
                report = data.get("report")
                result = {
                    "testId": test_id,
                    "status": status,
                    "targetUrl": target_url,
                    "uiMode": ui_mode,
                    "error": data.get("error"),
                    "report": report,
                    "reportUrl": f"{base}/api/v1/test/report/{test_id}",
                }
                if not args.json:
                    print("\n=== FAILED ===", file=sys.stderr)
                    print(f"Error: {data.get('error')}", file=sys.stderr)
                    if report:
                        print(f"Report: {report}", file=sys.stderr)
                if args.open_report:
                    _open_report(report, test_id, base)
                return emit_result(result, 1)
            time.sleep(3)

    if args.json:
        print(json.dumps({"status": "TIMEOUT", "error": "Test did not complete in time"}))
    else:
        print("TIMEOUT waiting for test completion", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
