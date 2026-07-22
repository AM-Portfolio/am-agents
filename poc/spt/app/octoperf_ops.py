from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import settings
from app.config_builder import snapshot_for_run
from app.metrics import extract_metrics_summary
from app.mcp_client import RemoteMcpClient

ROOT = Path(__file__).resolve().parents[1]
K6_SCRIPT = ROOT / "k6" / "smoke-get.js"
PLAYWRIGHT_SCRIPT = ROOT / "playwright" / "smoke-navigate.spec.ts"


def _client() -> RemoteMcpClient:
    return RemoteMcpClient(
        settings.octoperf_mcp_url,
        timeout_seconds=settings.mcp_timeout_seconds,
        bearer_token=settings.octoperf_mcp_token,
    )


def _pick_tool(tools: list[dict[str, Any]], *keywords: str) -> str | None:
    names = [t["name"] for t in tools]
    lower_map = {n.lower(): n for n in names}
    for kw in keywords:
        for low, orig in lower_map.items():
            if kw in low:
                return orig
    return None


async def ping() -> dict[str, Any]:
    client = _client()
    tools = await client.list_tools()
    return {
        "mcp_url": client.url,
        "tool_count": len(tools),
        "tools": [t["name"] for t in tools[:30]],
        "status": "ok",
    }


async def _import_script(
    *,
    source: str,
    content: str,
    filename: str,
    extra_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    client = _client()
    tools = await client.list_tools()
    tool = _pick_tool(tools, "import", source, "virtual")
    if not tool:
        raise RuntimeError(f"No import tool found. Available: {[t['name'] for t in tools]}")
    args: dict[str, Any] = {"source": source, "content": content, "filename": filename}
    if extra_args:
        args.update(extra_args)
    if settings.octoperf_workspace_id:
        args.setdefault("workspaceId", settings.octoperf_workspace_id)
    if settings.octoperf_project_id:
        args.setdefault("projectId", settings.octoperf_project_id)
    return await client.call_tool(tool, args)


async def import_k6_script(path: Path | None = None, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if payload:
        return await _import_script(
            source=payload.get("source", "k6"),
            content=payload.get("content", ""),
            filename=payload.get("filename", "script.js"),
            extra_args={k: v for k, v in payload.items() if k not in {"source", "content", "filename"}},
        )
    script_path = path or K6_SCRIPT
    return await _import_script(
        source="k6",
        content=script_path.read_text(encoding="utf-8"),
        filename=script_path.name,
    )


async def import_playwright_script(
    path: Path | None = None, *, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    if payload:
        return await _import_script(
            source=payload.get("source", "playwright"),
            content=payload.get("content", ""),
            filename=payload.get("filename", "spec.ts"),
            extra_args={k: v for k, v in payload.items() if k not in {"source", "content", "filename"}},
        )
    script_path = path or PLAYWRIGHT_SCRIPT
    return await _import_script(
        source="playwright",
        content=script_path.read_text(encoding="utf-8"),
        filename=script_path.name,
    )


async def run_bench(
    *,
    virtual_user_id: str | None = None,
    vus: int | None = None,
    duration: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    client = _client()
    tools = await client.list_tools()
    tool = _pick_tool(tools, "run", "bench", "start", "scenario")
    if not tool:
        raise RuntimeError(f"No run tool found. Available: {[t['name'] for t in tools]}")
    bench = payload or {}
    args: dict[str, Any] = {
        "vus": bench.get("vus") or vus or settings.smoke_vus,
        "duration": bench.get("duration") or duration or settings.smoke_duration,
    }
    vu = bench.get("virtualUserId") or bench.get("virtual_user_id") or virtual_user_id
    if vu:
        args["virtualUserId"] = vu
    project = bench.get("projectId") or bench.get("project_id") or settings.octoperf_project_id
    if project:
        args["projectId"] = project
    for k, v in bench.items():
        if k not in args and k not in {"virtual_user_id", "project_id"}:
            args[k] = v
    return await client.call_tool(tool, args)


async def get_status(run_id: str) -> dict[str, Any]:
    client = _client()
    tools = await client.list_tools()
    tool = _pick_tool(tools, "status", "progress", "monitor", "run")
    if not tool:
        raise RuntimeError(f"No status tool found. Available: {[t['name'] for t in tools]}")
    return await client.call_tool(tool, {"runId": run_id})


async def get_report(run_id: str) -> dict[str, Any]:
    client = _client()
    tools = await client.list_tools()
    tool = _pick_tool(tools, "report", "bench", "analyze", "metrics")
    if not tool:
        raise RuntimeError(f"No report tool found. Available: {[t['name'] for t in tools]}")
    return await client.call_tool(tool, {"runId": run_id})


def _extract_run_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("runId", "run_id", "id", "benchId", "bench_id"):
            if payload.get(key):
                return str(payload[key])
        for val in payload.values():
            found = _extract_run_id(val)
            if found:
                return found
    return None


def _extract_status(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("status", "state", "runStatus"):
            if payload.get(key):
                return str(payload[key]).lower()
        for val in payload.values():
            if isinstance(val, dict):
                s = _extract_status(val)
                if s:
                    return s
    return ""


async def poll_until_terminal(run_id: str, *, max_seconds: int | None = None) -> dict[str, Any]:
    deadline = time.monotonic() + (max_seconds or settings.smoke_poll_max_seconds)
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = await get_status(run_id)
        status = _extract_status(last)
        if status in {"succeeded", "success", "completed", "done", "failed", "error", "cancelled"}:
            return {"run_id": run_id, "status": status, "detail": last}
        await asyncio.sleep(10)
    return {"run_id": run_id, "status": "timeout", "detail": last}


def _payloads_used(config: dict[str, Any]) -> dict[str, Any]:
    payloads = config.get("payloads") or {}
    scripts = config.get("scripts") or {}
    k6 = dict(payloads.get("k6_import") or {})
    if not k6.get("content") and scripts.get("k6"):
        k6.setdefault("source", "k6")
        k6.setdefault("filename", "smoke-get.js")
        k6["content"] = scripts["k6"]
    pw = dict(payloads.get("playwright_import") or {})
    if not pw.get("content") and scripts.get("playwright"):
        pw.setdefault("source", "playwright")
        pw.setdefault("filename", "smoke-navigate.spec.ts")
        pw["content"] = scripts["playwright"]
    bench = dict(payloads.get("bench_run") or {})
    return {
        "k6_import": k6,
        "playwright_import": pw,
        "bench_run": bench,
        "har_stub": payloads.get("har_stub"),
    }


async def run_test_from_config(config: dict[str, Any]) -> dict[str, Any]:
    """Execute full test flow using stored config payloads; returns run record fields."""
    from datetime import datetime, timezone

    run_id_local = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    steps: list[dict[str, Any]] = []
    payloads_sent = _payloads_used(config)
    snapshot = snapshot_for_run(config)
    result: dict[str, Any] = {
        "id": run_id_local,
        "started_at": started,
        "status": "running",
        "passed": False,
        "config_id": config.get("id"),
        "config_name": config.get("name", "unnamed"),
        "target_url": config.get("target_url") or settings.poc_target_url,
        "config_snapshot": snapshot,
        "payloads_used": payloads_sent,
        "steps": steps,
        "octoperf_run_id": None,
        "metrics_summary": {},
        "report": None,
        "error": None,
    }

    async def step(name: str, coro, *, payload_key: str | None = None):
        try:
            payload = await coro
            entry: dict[str, Any] = {"step": name, "status": "pass", "detail": payload}
            if payload_key:
                entry["payload_sent"] = payloads_sent.get(payload_key)
            steps.append(entry)
            return payload
        except Exception as exc:
            entry = {"step": name, "status": "fail", "error": str(exc)}
            if payload_key:
                entry["payload_sent"] = payloads_sent.get(payload_key)
            steps.append(entry)
            raise

    try:
        await step("mcp_connect", ping())
        k6_import = await step(
            "import_k6", import_k6_script(payload=payloads_sent["k6_import"]), payload_key="k6_import"
        )
        pw_import = await step(
            "import_playwright",
            import_playwright_script(payload=payloads_sent["playwright_import"]),
            payload_key="playwright_import",
        )

        vu_id = None
        if isinstance(k6_import, dict):
            vu_id = k6_import.get("virtualUserId") or k6_import.get("virtual_user_id")
            if not vu_id and isinstance(k6_import.get("data"), dict):
                vu_id = k6_import["data"].get("virtualUserId")

        bench_payload = dict(payloads_sent["bench_run"])
        if vu_id:
            bench_payload["virtualUserId"] = vu_id

        run_payload = await step(
            "run_bench", run_bench(payload=bench_payload), payload_key="bench_run"
        )
        octo_run_id = _extract_run_id(run_payload)
        if not octo_run_id:
            raise RuntimeError(f"Could not extract run_id from: {run_payload}")

        result["octoperf_run_id"] = octo_run_id
        poll = await step("poll_status", poll_until_terminal(octo_run_id))
        report = await step("read_report", get_report(octo_run_id))

        result["passed"] = poll.get("status") in {"succeeded", "success", "completed", "done"}
        result["status"] = "passed" if result["passed"] else "failed"
        result["k6_import_result"] = k6_import
        result["playwright_import_result"] = pw_import
        result["bench_run_result"] = run_payload
        result["poll_result"] = poll
        result["report"] = report
        result["metrics_summary"] = extract_metrics_summary(report)
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)

    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    return result


async def run_smoke_test() -> dict[str, Any]:
    from app.config_builder import default_config_dict

    record = await run_test_from_config(default_config_dict())
    legacy = {
        "passed": record.get("passed", False),
        "run_id": record.get("octoperf_run_id"),
        "steps": record.get("steps", []),
        "error": record.get("error"),
        "report": record.get("report"),
        "local_run_id": record.get("id"),
    }
    if record.get("k6_import_result"):
        legacy["k6_import"] = record["k6_import_result"]
    if record.get("playwright_import_result"):
        legacy["playwright_import"] = record["playwright_import_result"]
    return legacy
