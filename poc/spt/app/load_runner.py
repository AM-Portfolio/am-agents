from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from app.artifact_store import persist_run_artifacts
from app.auth_resolver import ensure_auth_env, sanitize_auth_env
from app.catalog_loader import apis_for_config
from app.config import settings
from app.influx_metrics import build_spt_influx_lines
from app.metrics import extract_metrics_summary
from app.runners import process_registry
from app.script_generator import generate_k6_script
from app.trace_store import (
    build_api_index,
    capture_traces_http,
    load_summary_file,
    load_traces_file,
    redact_trace,
    save_api_index,
    save_traces_file,
)

ProgressCb = Callable[[dict[str, Any]], None]

_K6_PROGRESS_RE = re.compile(
    r"(?P<active>\d+)\s*/\s*(?P<maxvus>\d+)\s+VUs.*? (?P<done>\d+)\s+complete",
    re.IGNORECASE,
)
_K6_PCT_RE = re.compile(
    r"\[\s*(?P<pct>\d+)\s*%\s*\].*?(?P<active>\d+)\s+VUs",
    re.IGNORECASE,
)


def _planned_api_rows(apis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "api_id": a.get("id"),
            "name": a.get("name") or a.get("id"),
            "method": a.get("method") or "GET",
            "path": a.get("path") or "",
            "trace_available": False,
            "checks_passed": None,
            "request_count": None,
            "pass_count": None,
            "fail_count": None,
            "status": "running",
        }
        for a in apis
    ]


def _parse_k6_progress_line(line: str) -> dict[str, Any] | None:
    text = (line or "").strip()
    if not text:
        return None
    out: dict[str, Any] = {}
    m = _K6_PROGRESS_RE.search(text)
    if m:
        out["active_vus"] = int(m.group("active"))
        out["max_vus"] = int(m.group("maxvus"))
        out["completed_iterations"] = int(m.group("done"))
    m2 = _K6_PCT_RE.search(text)
    if m2:
        out["pct"] = int(m2.group("pct"))
        out.setdefault("active_vus", int(m2.group("active")))
    return out or None


def _run_k6_streaming(
    cmd: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    on_line: Callable[[str], None] | None = None,
    timeout_s: int = 720,
    run_id: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run k6 and stream stdout (incl. \\r progress redraws) for live UI updates."""
    if run_id:
        process_registry.register(run_id)
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=0,
    )
    if run_id:
        process_registry.attach_proc(run_id, proc)
    chunks: list[str] = []
    assert proc.stdout is not None

    def _emit(part: str) -> None:
        part = part.strip()
        if not part or not on_line:
            return
        try:
            on_line(part)
        except Exception:
            pass

    def _reader() -> None:
        buf = ""
        while True:
            ch = proc.stdout.read(1)
            if ch == "":
                break
            chunks.append(ch)
            if ch in ("\n", "\r"):
                _emit(buf)
                buf = ""
            else:
                buf += ch
                # emit mid-line progress periodically when buffer looks like a status line
                if len(buf) > 40 and ("VUs" in buf or "%" in buf) and len(buf) % 20 == 0:
                    _emit(buf)
        if buf:
            _emit(buf)

    t = threading.Thread(target=_reader, name="k6-stdout", daemon=True)
    t.start()
    try:
        rc = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=30)
        t.join(timeout=5)
        raise
    finally:
        if run_id:
            process_registry.unregister(run_id)
    t.join(timeout=30)
    return subprocess.CompletedProcess(cmd, rc, "".join(chunks), "")


def _parse_duration_seconds(duration: str) -> int:
    m = re.match(r"^(\d+)(s|m|h)$", (duration or "30s").strip())
    if not m:
        return 30
    n, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return n * 60
    if unit == "h":
        return n * 3600
    return n


def _cap_run_params(
    vus: int, duration: str, iterations: int | None = None
) -> tuple[int, str, int | None]:
    vus = min(max(1, vus), settings.max_vus)
    if iterations is not None:
        iterations = min(max(1, int(iterations)), 10_000)
        return vus, duration, iterations
    secs = min(_parse_duration_seconds(duration), settings.max_duration_seconds)
    if secs >= 60 and secs % 60 == 0:
        duration = f"{secs // 60}m"
    else:
        duration = f"{secs}s"
    return vus, duration, None


def _run_profile(config: dict[str, Any]) -> str:
    prof = (config.get("run_profile") or settings.default_run_profile or "load").lower()
    return prof if prof in ("debug", "load") else "load"


def _k6_script_from_config(
    config: dict[str, Any],
    apis: list[dict[str, Any]],
    profile: str,
    *,
    run_id: str | None = None,
) -> str:
    payloads = config.get("payloads") or {}
    k6 = payloads.get("k6_import") or {}
    if k6.get("content") and not apis:
        return str(k6["content"])
    scripts = config.get("scripts") or {}
    if scripts.get("k6") and not apis:
        return str(scripts["k6"])

    bench = dict(payloads.get("bench_run") or {})
    vus = int(bench.get("vus") or settings.smoke_vus)
    duration = str(bench.get("duration") or settings.smoke_duration)
    raw_iters = bench.get("iterations")
    iterations = int(raw_iters) if raw_iters is not None else None
    if profile == "debug":
        vus = 1
        iterations = 1
        duration = "1s"
    else:
        vus, duration, iterations = _cap_run_params(vus, duration, iterations)

    progress_url = None
    if run_id:
        root = (settings.root_path or "").rstrip("/")
        progress_url = f"http://127.0.0.1:{settings.app_port}{root}/api/runs/{run_id}/progress"

    # Always capture every call up to cap so the inspector can show per-call status.
    # (debug also keeps full bodies; load uses the same sample path.)
    return generate_k6_script(
        apis,
        service=str(config.get("service") or "unknown"),
        vus=vus,
        duration=duration,
        iterations=iterations,
        capture_traces=True,
        capture_failures=True,
        capture_all_calls=True,
        max_samples=settings.trace_max_calls,
        trace_body_max=settings.trace_body_max_bytes,
        progress_url=progress_url,
    )


async def push_influx(
    run_id: str,
    config: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    api_summary: list[dict[str, Any]] | None = None,
    *,
    status: str = "unknown",
    duration_s: float | None = None,
) -> bool:
    if not settings.influxdb_token:
        return False
    metrics = dict(metrics or {})
    # Allow callers to pass pass/fail counts via metrics bag
    lines = build_spt_influx_lines(
        run_id=run_id,
        config=config,
        metrics=metrics,
        api_summary=api_summary,
        status=status,
        duration_s=duration_s,
    )
    if not lines:
        return False
    url = f"{settings.influxdb_url.rstrip('/')}/api/v2/write"
    params = {"org": settings.influxdb_org, "bucket": settings.influxdb_bucket, "precision": "s"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                params=params,
                content="\n".join(lines),
                headers={
                    "Authorization": f"Token {settings.influxdb_token}",
                    "Content-Type": "text/plain; charset=utf-8",
                },
            )
            return r.status_code < 300
    except Exception:
        return False


async def run_k6_local(
    config: dict[str, Any],
    *,
    triggered_by: str = "manual",
    run_id: str | None = None,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    run_id = run_id or str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    process_registry.begin_run(run_id)
    profile = _run_profile(config)

    def _live(phase: str, message: str, **extra: Any) -> None:
        if progress:
            progress({"phase": phase, "message": message, **extra})

    _live("auth", "Logging in via identity…")
    try:
        config = await ensure_auth_env(config)
    except Exception as exc:
        process_registry.unregister(run_id)
        process_registry.clear_cancelled(run_id)
        return {
            "id": run_id,
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "passed": False,
            "runner": "k6-local",
            "run_profile": profile,
            "config_name": config.get("name", "unnamed"),
            "service": config.get("service", "am-analysis"),
            "environment": config.get("environment", settings.default_environment),
            "test_type": config.get("test_type", "k6"),
            "triggered_by": triggered_by,
            "target_url": config.get("target_url") or settings.poc_target_url,
            "api_count": 0,
            "payloads_used": {"bench_run": {}},
            "steps": [{"step": "auth", "status": "fail", "error": str(exc)}],
            "metrics_summary": {},
            "api_summary": [],
            "live": {"phase": "auth", "message": f"Auth failed: {exc}"},
            "error": f"Auth failed: {exc}",
        }
    payloads = config.get("payloads") or {}
    bench = dict(payloads.get("bench_run") or {})
    base_url, apis = apis_for_config(config, run_id=run_id)
    target = base_url or config.get("target_url") or settings.poc_target_url

    vus = int(bench.get("vus") or settings.smoke_vus)
    duration = str(bench.get("duration") or settings.smoke_duration)
    raw_iters = bench.get("iterations")
    iterations = int(raw_iters) if raw_iters is not None else None
    if profile == "debug":
        vus = 1
        bench["vus"] = 1
        bench["iterations"] = 1
        bench["duration"] = "1s"
    else:
        vus, duration, iterations = _cap_run_params(vus, duration, iterations)
        bench["vus"] = vus
        if iterations is not None:
            bench["iterations"] = iterations
            bench.pop("duration", None)
        else:
            bench.pop("iterations", None)
            bench["duration"] = duration
    config.setdefault("payloads", {})["bench_run"] = bench

    script = _k6_script_from_config(config, apis, profile, run_id=run_id)
    steps: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "id": run_id,
        "started_at": started,
        "status": "running",
        "passed": False,
        "runner": "k6-local",
        "run_profile": profile,
        "config_id": config.get("id"),
        "config_name": config.get("name", "unnamed"),
        "service": config.get("service", "am-analysis"),
        "environment": config.get("environment", settings.default_environment),
        "test_type": config.get("test_type", "k6"),
        "triggered_by": triggered_by,
        "target_url": target,
        "api_count": len(apis),
        "payloads_used": {
            # Do not store generated k6 script (contains JWTs + unreadable in UI)
            "k6_import": {},
            "playwright_import": payloads.get("playwright_import") or {},
            "bench_run": bench,
            "auth_env": sanitize_auth_env(payloads.get("auth_env")),
            "run_params": {
                "profile": profile,
                "vus": bench.get("vus"),
                "duration": bench.get("duration"),
                "iterations": bench.get("iterations"),
                "api_count": len(apis),
                "max_vus_cap": settings.max_vus,
                "max_duration_cap_s": settings.max_duration_seconds,
                "triggered_by": triggered_by,
            },
            "har_stub": payloads.get("har_stub"),
            "api_overrides": payloads.get("api_overrides") or [],
            "apis_tested": [
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "method": a.get("method"),
                    "path": a.get("path"),
                    "query": a.get("query") or {},
                }
                for a in apis
            ],
        },
        "steps": steps,
        "metrics_summary": {},
        "api_summary": _planned_api_rows(apis),
        "report": None,
        "grafana_url": None,
        "artifacts": [],
        "error": None,
        "live": {
            "phase": "prepare",
            "message": f"Prepared {len(apis)} APIs — starting k6 ({bench.get('vus')} VUs)…",
            "vus": bench.get("vus"),
            "iterations": bench.get("iterations"),
            "duration": bench.get("duration"),
            "api_count": len(apis),
            "completed_iterations": 0,
            "total_iterations": bench.get("iterations"),
            "pct": 0,
        },
    }
    # Push planned API rows so UI shows endpoints immediately
    _live(
        "prepare",
        result["live"]["message"],
        vus=bench.get("vus"),
        iterations=bench.get("iterations"),
        duration=bench.get("duration"),
        api_count=len(apis),
        completed_iterations=0,
        total_iterations=bench.get("iterations"),
        pct=0,
        api_summary=result["api_summary"],
    )

    k6_bin = settings.k6_bin
    if not Path(k6_bin).is_file():
        steps.append({"step": "k6_run", "status": "fail", "error": f"k6 not found at {k6_bin}"})
        result["status"] = "failed"
        result["error"] = "k6 binary missing"
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        return result

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script_path = tmp_path / "test.js"
        script_path.write_text(script, encoding="utf-8")
        env = {
            **os.environ,
            "POC_TARGET_URL": target,
            "POC_BASE_URL": target,
        }
        root = (settings.root_path or "").rstrip("/")
        env["SPT_PROGRESS_URL"] = f"http://127.0.0.1:{settings.app_port}{root}/api/runs/{run_id}/progress"
        env["SPT_SAMPLE_URL"] = f"http://127.0.0.1:{settings.app_port}{root}/api/runs/{run_id}/sample"
        cmd = [k6_bin, "run", str(script_path)]
        try:
            steps.append(
                {
                    "step": "k6_run",
                    "status": "running",
                    "detail": {
                        "vus": bench.get("vus"),
                        "duration": bench.get("duration"),
                        "iterations": bench.get("iterations"),
                        "profile": profile,
                        "api_count": len(apis),
                    },
                }
            )
            total_iters = bench.get("iterations")
            last_progress: dict[str, Any] = {
                "completed_iterations": 0,
                "total_iterations": total_iters,
                "pct": 0,
                "active_vus": bench.get("vus"),
            }

            def _on_k6_line(line: str) -> None:
                parsed = _parse_k6_progress_line(line)
                if not parsed:
                    return
                last_progress.update(parsed)
                # Prefer HTTP progress callbacks when present (more accurate / finer-grained)
                try:
                    from app.run_store import get_run

                    cur = (get_run(run_id) or {}).get("live") or {}
                    if int(cur.get("api_hits") or 0) > 0 or int(cur.get("completed_iterations") or 0) > 0:
                        return
                except Exception:
                    pass
                done = last_progress.get("completed_iterations")
                pct = last_progress.get("pct")
                if pct is None and total_iters and done is not None:
                    pct = min(99, int(round(100.0 * float(done) / float(total_iters))))
                    last_progress["pct"] = pct
                msg = "k6 running"
                if done is not None and total_iters:
                    msg = f"k6 progress — {done}/{total_iters} iterations"
                elif done is not None:
                    msg = f"k6 progress — {done} iterations complete"
                elif pct is not None:
                    msg = f"k6 progress — {pct}%"
                if last_progress.get("active_vus") is not None:
                    msg += f" · {last_progress['active_vus']} VUs"
                _live(
                    "k6",
                    msg,
                    vus=bench.get("vus"),
                    iterations=total_iters,
                    duration=bench.get("duration"),
                    api_count=len(apis),
                    completed_iterations=done,
                    total_iterations=total_iters,
                    pct=pct,
                    active_vus=last_progress.get("active_vus"),
                    max_vus=last_progress.get("max_vus") or bench.get("vus"),
                    api_summary=result["api_summary"],
                )

            _live(
                "k6",
                f"k6 starting — {bench.get('vus')} VUs"
                + (f", {bench.get('iterations')} calls" if bench.get("iterations") else f", {bench.get('duration')}"),
                vus=bench.get("vus"),
                iterations=bench.get("iterations"),
                duration=bench.get("duration"),
                api_count=len(apis),
                completed_iterations=0,
                total_iterations=total_iters,
                api_hits=0,
                pct=0,
                api_summary=result["api_summary"],
            )

            stop_heartbeat = threading.Event()

            def _heartbeat() -> None:
                from app.run_store import get_run, update_run

                started_ts = datetime.now(timezone.utc)
                while not stop_heartbeat.wait(1.0):
                    row = get_run(run_id)
                    if not row or row.get("status") != "running":
                        continue
                    elapsed = int((datetime.now(timezone.utc) - started_ts).total_seconds())
                    live = dict(row.get("live") or {})
                    live["elapsed_s"] = elapsed
                    live["phase"] = live.get("phase") or "k6"
                    live["heartbeat_at"] = datetime.now(timezone.utc).isoformat()
                    base = live.get("message") or "k6 running…"
                    # Keep counters from k6 callbacks; only refresh elapsed suffix
                    core = base.split(" · elapsed ")[0]
                    live["message"] = f"{core} · elapsed {elapsed}s"
                    update_run(run_id, {"live": live, "status": "running"})

            hb = threading.Thread(target=_heartbeat, name="k6-heartbeat", daemon=True)
            hb.start()
            try:
                proc = await asyncio.to_thread(
                    _run_k6_streaming,
                    cmd,
                    cwd=tmp,
                    env=env,
                    on_line=_on_k6_line,
                    timeout_s=settings.max_duration_seconds + 120,
                    run_id=run_id,
                )
            finally:
                stop_heartbeat.set()
                hb.join(timeout=2)

            from app.run_store import get_run as _get_run_now

            cancelled = process_registry.is_cancel_requested(run_id) or (
                (_get_run_now(run_id) or {}).get("status") == "cancelled"
            )
            process_registry.clear_cancelled(run_id)
            if cancelled:
                steps.append({"step": "k6_run", "status": "fail", "error": "stopped by user"})
                result["status"] = "cancelled"
                result["passed"] = False
                result["error"] = "stopped by user"
                result["live"] = {"phase": "cancelled", "message": "Stopped by user"}
            else:
                _live("collect", "Collecting summary / traces…", pct=99, api_summary=result["api_summary"])
                summary_path = tmp_path / "summary.json"
                traces_path = tmp_path / "traces.json"
                sample_traces_path = Path(settings.data_dir) / "artifacts" / run_id / "traces.json"
                report = load_summary_file(summary_path) if summary_path.is_file() else {}
                traces = load_traces_file(traces_path)
                # Samples posted live from k6 VUs land in artifacts/traces.json (one per call)
                samples = load_traces_file(sample_traces_path)
                if samples:
                    by_idx: dict[int, dict[str, Any]] = {}
                    no_idx: list[dict[str, Any]] = []
                    for sample in samples:
                        raw_idx = sample.get("call_index")
                        if raw_idx is not None:
                            try:
                                by_idx[int(raw_idx)] = sample
                            except (TypeError, ValueError):
                                no_idx.append(sample)
                        else:
                            no_idx.append(sample)
                    if by_idx:
                        traces = [by_idx[k] for k in sorted(by_idx.keys())] + no_idx
                    else:
                        traces = samples
                    if len(traces) > settings.trace_max_calls:
                        traces = traces[: settings.trace_max_calls]
                if profile == "debug" and not traces:
                    traces = await capture_traces_http(
                        target,
                        apis,
                        body_max=settings.trace_body_max_bytes,
                    )
                    save_traces_file(traces_path, traces)
                if traces:
                    save_traces_file(sample_traces_path, traces)
                    save_traces_file(traces_path, traces)
                api_index = build_api_index(traces, report, apis)
                index_bytes = json.dumps(api_index, indent=2, default=str).encode("utf-8")
                save_api_index(Path(settings.data_dir) / "artifacts" / run_id / "api-index.json", api_index)

                artifact_files: dict[str, bytes] = {"api-index.json": index_bytes}
                if summary_path.is_file():
                    artifact_files["summary.json"] = summary_path.read_bytes()
                if traces_path.is_file() or sample_traces_path.is_file():
                    src = traces_path if traces_path.is_file() else sample_traces_path
                    artifact_files["traces.json"] = src.read_bytes()
                artifacts = await persist_run_artifacts(
                    run_id,
                    str(config.get("service") or "unknown"),
                    artifact_files,
                )

                if proc.returncode != 0:
                    err_tail = (proc.stdout or proc.stderr or "")[-2000:]
                    steps[-1] = {
                        "step": "k6_run",
                        "status": "fail",
                        "error": err_tail if err_tail else f"exit {proc.returncode}",
                    }
                    result["status"] = "failed"
                    result["error"] = steps[-1]["error"]
                    # Still collect whatever summary we have for Grafana
                    metrics = extract_metrics_summary(report) or _metrics_from_k6_summary(report)
                    result["metrics_summary"] = metrics
                    result["api_summary"] = api_index
                    result["api_count"] = len(api_index)
                    result["api_pass_count"] = len([a for a in api_index if a.get("checks_passed")])
                    result["api_fail_count"] = len([a for a in api_index if a.get("checks_passed") is False])
                    result["artifacts"] = artifacts
                else:
                    steps[-1] = {
                        "step": "k6_run",
                        "status": "pass",
                        "detail": {"exit_code": 0, "apis_tested": len(api_index)},
                    }
                    metrics = extract_metrics_summary(report)
                    if not metrics and report:
                        metrics = _metrics_from_k6_summary(report)
                    failed = [a for a in api_index if not a.get("checks_passed")]
                    passed_apis = [a for a in api_index if a.get("checks_passed")]
                    result["report"] = report
                    result["metrics_summary"] = metrics
                    result["api_summary"] = api_index
                    result["api_count"] = len(api_index)
                    result["api_pass_count"] = len(passed_apis)
                    result["api_fail_count"] = len(failed)
                    result["passed"] = len(failed) == 0
                    result["status"] = "passed" if result["passed"] else "failed"
                    if failed and passed_apis:
                        result["error"] = f"{len(failed)} of {len(api_index)} API(s) failed ({len(passed_apis)} passed)"
                    elif failed:
                        result["error"] = f"{len(failed)} API(s) failed checks"
                    result["artifacts"] = artifacts
        except subprocess.TimeoutExpired:
            steps.append({"step": "k6_run", "status": "fail", "error": "timeout"})
            result["status"] = "failed"
            result["error"] = "k6 run timed out"
        except Exception as exc:
            steps.append({"step": "k6_run", "status": "fail", "error": str(exc)})
            result["status"] = "failed"
            result["error"] = str(exc)

    if config.get("test_type") in {"playwright", "mixed"}:
        steps.append(
            {
                "step": "playwright",
                "status": "skip",
                "detail": "Install Testkube workflow for Playwright runs (see catalog/spt/workflows/)",
            }
        )

    finished = datetime.now(timezone.utc).isoformat()
    result["finished_at"] = finished
    result["live"] = {
        "phase": "done",
        "message": f"Finished — {result.get('status')}",
    }
    result["grafana_url"] = __import__("app.grafana_links", fromlist=["grafana_run_url"]).grafana_run_url(
        service=result.get("service"),
        environment=result.get("environment"),
        started_at=result.get("started_at"),
        finished_at=finished,
        run_id=run_id,
    )
    # Always push a run summary point (passed / failed / cancelled) when token is set
    try:
        started_dt = datetime.fromisoformat(str(result.get("started_at") or started).replace("Z", "+00:00"))
        duration_s = max(0.0, (datetime.now(timezone.utc) - started_dt).total_seconds())
    except Exception:
        duration_s = None
    metrics_bag = dict(result.get("metrics_summary") or {})
    if result.get("api_pass_count") is not None:
        metrics_bag["api_pass_count"] = result["api_pass_count"]
    if result.get("api_fail_count") is not None:
        metrics_bag["api_fail_count"] = result["api_fail_count"]
    await push_influx(
        run_id,
        {
            **config,
            "name": config.get("name") or result.get("config_name") or "unnamed",
            "config_name": result.get("config_name") or config.get("name") or "unnamed",
            "service": config.get("service") or result.get("service"),
            "environment": config.get("environment") or result.get("environment"),
            "run_profile": config.get("run_profile") or result.get("run_profile"),
        },
        metrics_bag,
        result.get("api_summary") or [],
        status=str(result.get("status") or "unknown"),
        duration_s=duration_s,
    )
    return result


def get_run_trace(run_id: str, api_id: str, *, redact: bool = True) -> dict[str, Any] | None:
    """Return one representative trace for an API (prefer failure)."""
    traces_path = Path(settings.data_dir) / "artifacts" / run_id / "traces.json"
    chosen: dict[str, Any] | None = None
    for row in load_traces_file(traces_path):
        if str(row.get("api_id")) != api_id:
            continue
        if chosen is None or (chosen.get("checks_passed") and not row.get("checks_passed")):
            chosen = row
    if chosen is None:
        return None
    return redact_trace(chosen) if redact else chosen


def list_run_traces(
    run_id: str,
    *,
    api_id: str | None = None,
    failed_only: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Return per-call trace summaries for the inspector list."""
    traces_path = Path(settings.data_dir) / "artifacts" / run_id / "traces.json"
    rows = load_traces_file(traces_path)
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        aid = str(row.get("api_id") or "")
        if api_id and aid != api_id:
            continue
        passed = bool(row.get("checks_passed"))
        if failed_only and passed:
            continue
        res = row.get("response") or {}
        timings = row.get("timings") or {}
        out.append(
            {
                "index": i,
                "call_index": row.get("call_index") if row.get("call_index") is not None else i + 1,
                "api_id": aid,
                "name": row.get("name") or aid,
                "method": row.get("method") or "GET",
                "path": row.get("path") or "",
                "url": row.get("url") or "",
                "checks_passed": passed,
                "status": res.get("status"),
                "duration_ms": timings.get("duration_ms"),
                "vu": row.get("vu"),
                "iter": row.get("iter"),
            }
        )
    total = len(out)
    return out[offset : offset + limit], total


def get_run_trace_at(run_id: str, index: int, *, redact: bool = True) -> dict[str, Any] | None:
    traces_path = Path(settings.data_dir) / "artifacts" / run_id / "traces.json"
    rows = load_traces_file(traces_path)
    if index < 0 or index >= len(rows):
        return None
    row = rows[index]
    return redact_trace(row) if redact else row


def get_run_api_index(run_id: str) -> list[dict[str, Any]]:
    path = Path(settings.data_dir) / "artifacts" / run_id / "api-index.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []

def _metrics_from_k6_summary(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics") or report
    out: dict[str, Any] = {}
    for key, val in metrics.items() if isinstance(metrics, dict) else []:
        if not isinstance(val, dict):
            continue
        if key == "http_reqs" and "rate" in val:
            out["throughput.requestsPerSecond"] = round(float(val["rate"]), 2)
        if key == "http_req_duration":
            if "med" in val:
                out["responseTime.p50"] = round(float(val["med"]), 2)
            if "p(90)" in val:
                out["responseTime.p90"] = round(float(val["p(90)"]), 2)
            if "p(95)" in val:
                out["responseTime.p95"] = round(float(val["p(95)"]), 2)
            if "p(99)" in val:
                out["responseTime.p99"] = round(float(val["p(99)"]), 2)
            if "avg" in val:
                out["responseTime.avg"] = round(float(val["avg"]), 2)
        if key == "http_req_failed" and "rate" in val:
            # k6 rate is 0..1 → percent for SPT dashboards
            out["errorRate"] = round(float(val["rate"]) * 100, 2)
    return out
