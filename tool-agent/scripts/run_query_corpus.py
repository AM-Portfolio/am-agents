#!/usr/bin/env python3
"""Run normal + advanced NL query corpus against parse_rules (local) or HTTP (preprod)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_ROOT))

from app.config import settings  # noqa: E402
from app.schema.loader import reset_schema_catalog  # noqa: E402
from tools._loader import get_tool  # noqa: E402
from tools._shared.intent_trace import clear_resolve_trace, get_resolve_trace  # noqa: E402
from tools._shared.resolve import ParamResolutionError, resolve_intent_params  # noqa: E402


def _post(base: str, path: str, body: dict, *, caller: str | None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if caller:
        headers["X-Agent-Caller"] = caller
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": e.read().decode()[:300]}


def _run_local(item: dict) -> tuple[bool, str, dict]:
    backend = item.get("backend")
    query = item["query"]
    tool = get_tool(backend) if backend else None
    report: dict = {"label": item.get("label"), "backend": backend, "query": query}
    if not tool:
        return False, f"unknown backend {backend}", report
    intent = tool.parse_rules(query, backend)
    if not intent:
        report["stage"] = "parse_rules"
        return False, "parse_rules returned None", report
    report["operation"] = intent.operation
    report["confidence"] = intent.confidence
    report["parse_source"] = "rules"
    if item.get("expect_operation") and intent.operation != item["expect_operation"]:
        return False, f"operation {intent.operation} != {item['expect_operation']}", report
    if item.get("min_confidence") and intent.confidence < float(item["min_confidence"]):
        return False, f"confidence {intent.confidence} below {item['min_confidence']}", report
    if item.get("resolve"):
        clear_resolve_trace()
        try:
            resolved, entity = resolve_intent_params(intent, query_text=query)
            if tool:
                resolved, entity = tool.resolve(resolved, query)
        except ParamResolutionError as exc:
            report["stage"] = "resolve"
            return False, f"resolve failed: {exc.message}", report
        report["entity"] = entity
        report["params"] = dict(resolved.params)
        report.update(get_resolve_trace())
        for key in item.get("expect_params") or []:
            if not resolved.params.get(key):
                return False, f"missing resolved param {key}", report
    return True, f"{intent.backend}.{intent.operation} conf={intent.confidence:.2f}", report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default=str(AGENT_ROOT / "scripts" / "query_corpus.yaml"))
    parser.add_argument("--local", action="store_true", help="Run parse_rules + optional resolve only")
    parser.add_argument("--preprod", action="store_true", help="HTTP against preprod")
    parser.add_argument("--base", default="https://am.asrax.in/tools")
    parser.add_argument("--mode", choices=("plan", "query"), default="plan")
    parser.add_argument("--tier", choices=("normal", "advanced", "all"), default="all")
    parser.add_argument("--agent-caller", default="corpus-test")
    parser.add_argument("--report", help="Write JSON report to this path (local mode)")
    args = parser.parse_args()

    with open(args.corpus, encoding="utf-8") as f:
        corpus = yaml.safe_load(f) or {}

    tiers: list[tuple[str, list]] = []
    if args.tier in ("normal", "all"):
        tiers.append(("normal", corpus.get("normal") or []))
    if args.tier in ("advanced", "all"):
        tiers.append(("advanced", corpus.get("advanced") or []))

    if args.local:
        reset_schema_catalog()
        passed = failed = 0
        report_rows: list[dict] = []
        for tier_name, items in tiers:
            for item in items:
                ok, detail, row = _run_local(item)
                row["tier"] = tier_name
                row["ok"] = ok
                row["detail"] = detail
                report_rows.append(row)
                label = item.get("label", item["query"][:40])
                print(f"{'PASS' if ok else 'FAIL'} [{tier_name}] {label} — {detail}")
                passed += ok
                failed += not ok
        total = passed + failed
        print(f"\n{passed}/{total} passed (local)")
        if args.report:
            out = {
                "env": settings.APP_ENV,
                "passed": passed,
                "failed": failed,
                "total": total,
                "results": report_rows,
            }
            Path(args.report).write_text(json.dumps(out, indent=2), encoding="utf-8")
            print(f"Report written to {args.report}")
        return 0 if failed == 0 else 1

    if not args.preprod:
        print("Specify --local or --preprod")
        return 2

    path = f"/api/v1/tools/{args.mode}"
    passed = failed = 0
    for tier_name, items in tiers:
        for item in items:
            body = {
                "query": item["query"],
                "backend": item.get("backend"),
                "read_only": True,
            }
            status, payload = _post(args.base, path, body, caller=args.agent_caller)
            ok = status == 200
            if ok and args.mode == "plan":
                ok = bool((payload.get("intent") or {}).get("backend"))
            if ok and args.mode == "query":
                ok = bool(payload.get("backend"))
            if ok and item.get("expect_operation"):
                op = (payload.get("intent") or payload).get("operation")
                ok = op == item["expect_operation"]
            label = item.get("label", item["query"][:40])
            detail = payload.get("detail") if not ok else (
                f"{(payload.get('intent') or payload).get('backend')}."
                f"{(payload.get('intent') or payload).get('operation')}"
            )
            print(f"{'PASS' if ok else 'FAIL'} [{tier_name}] {label} [{status}] {detail}")
            passed += ok
            failed += not ok

    total = passed + failed
    print(f"\n{passed}/{total} passed ({args.mode} @ {args.base})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
