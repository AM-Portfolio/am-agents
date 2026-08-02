#!/usr/bin/env python3
"""
Golden eval runner for finance AI chat.

Hits am-ai-gateway (or direct fin-agent) with cases from eval/fin_chat_golden.json.
Thick evaluators: HTTP 200, widgetId, non-empty required widgetParams, toolsUsed rules.
One retry per item on failure (flake budget).

Usage:
  set EVAL_GATEWAY_URL=https://am-dev.asrax.in/ai
  set EVAL_USER_ID=<fixture-user-id>
  python scripts/eval_fin_chat.py

Optional:
  EVAL_BEARER_TOKEN=...   # when AUTH_REQUIRED=true
  EVAL_SESSION_ID=...     # reuse session; default new UUID per run
  EVAL_GOLDEN_PATH=...    # default: ../eval/fin_chat_golden.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = ROOT / "eval" / "fin_chat_golden.json"


def _non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def evaluate_item(
    *,
    status_code: int,
    body: dict[str, Any],
    expected: dict[str, Any],
) -> list[str]:
    """Return list of failure reasons (empty = pass)."""
    failures: list[str] = []
    if status_code != 200:
        failures.append(f"http_status={status_code} expected=200")
        return failures

    want_widget = expected.get("widgetId")
    got_widget = body.get("widgetId")
    if want_widget and got_widget != want_widget:
        failures.append(f"widgetId={got_widget!r} expected={want_widget!r}")

    params = body.get("widgetParams") or {}
    if not isinstance(params, dict):
        failures.append("widgetParams is not an object")
        params = {}

    for key in expected.get("requiredWidgetParams") or []:
        if key not in params or not _non_empty(params.get(key)):
            failures.append(f"widgetParams[{key!r}] missing or empty")

    tools = body.get("toolsUsed") or []
    if not isinstance(tools, list):
        failures.append("toolsUsed is not a list")
        tools = []

    if expected.get("requireToolsUsed"):
        if not tools:
            failures.append("toolsUsed empty but requireToolsUsed=true")
        any_tools = expected.get("requiredToolsAny") or []
        if any_tools and not any(t in tools for t in any_tools):
            failures.append(f"toolsUsed={tools} missing any of {any_tools}")

    if not body.get("traceId"):
        failures.append("traceId missing")
    if not body.get("sessionId"):
        failures.append("sessionId missing")

    return failures


def run_one(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    user_id: str,
    session_id: str,
    message: str,
) -> tuple[int, dict[str, Any]]:
    payload = {
        "message": message,
        "userId": user_id,
        "sessionId": session_id,
    }
    resp = client.post(url, json=payload, headers=headers, timeout=90.0)
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {"_raw": resp.text[:500]}
    if not isinstance(body, dict):
        body = {"_raw": body}
    return resp.status_code, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Finance chat golden eval")
    parser.add_argument(
        "--gateway-url",
        default=os.getenv("EVAL_GATEWAY_URL", "https://am-dev.asrax.in/ai"),
        help="am-ai-gateway base URL",
    )
    parser.add_argument(
        "--chat-path",
        default=os.getenv("EVAL_CHAT_PATH", "/api/v1/ai/chat"),
    )
    parser.add_argument(
        "--user-id",
        default=os.getenv("EVAL_USER_ID", ""),
        help="Fixture user id (required for data widgets)",
    )
    parser.add_argument(
        "--bearer",
        default=os.getenv("EVAL_BEARER_TOKEN", ""),
        help="Optional Bearer token when AUTH_REQUIRED=true",
    )
    parser.add_argument(
        "--golden",
        default=os.getenv("EVAL_GOLDEN_PATH", str(DEFAULT_GOLDEN)),
    )
    parser.add_argument(
        "--session-id",
        default=os.getenv("EVAL_SESSION_ID", ""),
    )
    args = parser.parse_args()

    if not args.user_id:
        print("ERROR: EVAL_USER_ID / --user-id is required (fixture portfolio user).", file=sys.stderr)
        print("Set EVAL_USER_ID to a known dev user — see docs/RELEASE_GATE.md.", file=sys.stderr)
        return 2

    golden_path = Path(args.golden)
    if not golden_path.exists():
        print(f"ERROR: golden file not found: {golden_path}", file=sys.stderr)
        return 2

    data = json.loads(golden_path.read_text(encoding="utf-8"))
    items = data.get("items") or []
    session_id = args.session_id or str(uuid.uuid4())
    url = args.gateway_url.rstrip("/") + args.chat_path

    headers = {
        "Content-Type": "application/json",
        "X-Request-Id": str(uuid.uuid4()),
        "X-Session-Id": session_id,
    }
    if args.bearer:
        headers["Authorization"] = f"Bearer {args.bearer}"

    print(f"Gateway: {url}")
    print(f"User:    {args.user_id}")
    print(f"Session: {session_id}")
    print(f"Items:   {len(items)}")
    print("---")

    passed = 0
    failed = 0
    results: list[dict[str, Any]] = []

    with httpx.Client() as client:
        for item in items:
            item_id = item.get("id", "?")
            message = (item.get("input") or {}).get("message", "")
            expected = item.get("expected") or {}
            headers["X-Request-Id"] = str(uuid.uuid4())

            status, body = run_one(
                client, url, headers, args.user_id, session_id, message
            )
            failures = evaluate_item(status_code=status, body=body, expected=expected)

            retried = False
            if failures:
                # Flake budget: one retry
                retried = True
                headers["X-Request-Id"] = str(uuid.uuid4())
                status, body = run_one(
                    client, url, headers, args.user_id, session_id, message
                )
                failures = evaluate_item(status_code=status, body=body, expected=expected)

            ok = not failures
            if ok:
                passed += 1
                flag = "PASS" + (" (retry)" if retried else "")
            else:
                failed += 1
                flag = "FAIL" + (" (after retry)" if retried else "")

            print(
                f"[{flag}] {item_id}: widgetId={body.get('widgetId')} "
                f"tools={body.get('toolsUsed')} traceId={body.get('traceId')}"
            )
            if failures:
                for f in failures:
                    print(f"         - {f}")

            results.append(
                {
                    "id": item_id,
                    "ok": ok,
                    "retried": retried,
                    "status_code": status,
                    "widgetId": body.get("widgetId"),
                    "toolsUsed": body.get("toolsUsed"),
                    "traceId": body.get("traceId"),
                    "failures": failures,
                }
            )

    print("---")
    print(f"Result: {passed}/{len(items)} passed, {failed} failed")
    out_path = ROOT / "eval" / "last_eval_result.json"
    out_path.write_text(
        json.dumps(
            {
                "gateway": url,
                "userId": args.user_id,
                "sessionId": session_id,
                "passed": passed,
                "failed": failed,
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {out_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
