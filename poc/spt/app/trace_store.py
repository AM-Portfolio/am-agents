from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_REDACT_HEADERS = frozenset(
    h.lower()
    for h in (
        "authorization",
        "cookie",
        "x-api-key",
        "x-auth-token",
        "proxy-authorization",
    )
)

_REDACT_PATTERN = re.compile(
    r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*|"
    r"(token['\"]?\s*[:=]\s*['\"]?)[A-Za-z0-9\-._~+/]+",
    re.IGNORECASE,
)


def redact_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        if str(k).lower() in _REDACT_HEADERS:
            out[str(k)] = "***redacted***"
        else:
            out[str(k)] = str(v)
    return out


def redact_body(body: Any) -> Any:
    if body is None:
        return None
    s = str(body)
    return _REDACT_PATTERN.sub(r"\1***redacted***", s)


def redact_trace(trace: dict[str, Any]) -> dict[str, Any]:
    req = trace.get("request") or {}
    resp = trace.get("response") or {}
    return {
        **trace,
        "request": {
            **req,
            "headers": redact_headers(req.get("headers")),
            "body": redact_body(req.get("body")),
        },
        "response": {
            **resp,
            "headers": redact_headers(resp.get("headers")),
            "body": redact_body(resp.get("body")),
        },
    }


def _group_metrics(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract per-api stats from k6 summary group tree."""
    out: dict[str, dict[str, Any]] = {}

    def walk(group: dict[str, Any], prefix: str = "") -> None:
        name = group.get("name") or prefix
        checks = group.get("checks") or {}
        if name and name != "::setup" and name != "::teardown":
            passed = 0
            failed = 0
            if isinstance(checks, list):
                check_items = checks
            elif isinstance(checks, dict):
                check_items = checks.values()
            else:
                check_items = []
            for chk in check_items:
                if isinstance(chk, dict):
                    passed += int(chk.get("passes", 0) or 0)
                    failed += int(chk.get("fails", 0) or 0)
            duration = group.get("duration") or {}
            calls = passed + failed
            row = {
                "api_id": name,
                "checks_passed": failed == 0 and passed > 0,
                "check_passes": passed,
                "check_fails": failed,
                "pass_count": passed,
                "fail_count": failed,
                "request_count": calls if calls > 0 else None,
                "error_rate": round((failed / calls) * 100, 2) if calls else 0.0,
            }
            if duration.get("avg") is not None and float(duration.get("avg") or 0) > 0:
                row["duration_ms"] = round(float(duration.get("avg") or 0), 2)
            if duration.get("p(90)") is not None and float(duration.get("p(90)") or 0) > 0:
                row["duration_p90_ms"] = round(float(duration.get("p(90)") or 0), 2)
            if duration.get("min") is not None:
                row["duration_min_ms"] = round(float(duration.get("min") or 0), 2)
            if duration.get("max") is not None:
                row["duration_max_ms"] = round(float(duration.get("max") or 0), 2)
            out[name] = row
        for child in group.get("groups") or []:
            if isinstance(child, dict):
                walk(child, child.get("name", ""))

    root = summary.get("root_group") or {}
    if isinstance(root, dict):
        for child in root.get("groups") or []:
            if isinstance(child, dict):
                walk(child)
    return out


def _safe_metric_id(api_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", str(api_id or "api"))


def _metrics_by_api_name(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Parse per-API metrics named spt_dur_<id>, spt_http_<id>, etc."""
    out: dict[str, dict[str, Any]] = {}
    metrics = summary.get("metrics") or {}
    prefixes = (
        ("spt_dur_", "duration"),
        ("spt_http_", "http"),
        ("spt_reqs_", "reqs"),
        ("spt_fails_", "fails"),
    )
    for key, val in metrics.items():
        if not isinstance(val, dict):
            continue
        key_s = str(key)
        for prefix, kind in prefixes:
            if not key_s.startswith(prefix):
                continue
            safe = key_s[len(prefix) :]
            if not safe or "{" in safe:
                continue
            row = out.setdefault(safe, {"_safe": safe})
            values = val.get("values") or val
            if not isinstance(values, dict):
                continue
            if kind == "duration":
                if values.get("avg") is not None:
                    row["duration_ms"] = round(float(values.get("avg") or 0), 2)
                if values.get("p(90)") is not None:
                    row["duration_p90_ms"] = round(float(values.get("p(90)") or 0), 2)
                if values.get("min") is not None:
                    row["duration_min_ms"] = round(float(values.get("min") or 0), 2)
                if values.get("max") is not None:
                    row["duration_max_ms"] = round(float(values.get("max") or 0), 2)
            elif kind == "http":
                # Gauge last/value
                status = values.get("value")
                if status is None:
                    status = values.get("max") or values.get("avg")
                if status is not None:
                    try:
                        row["status"] = int(round(float(status)))
                    except (TypeError, ValueError):
                        pass
            elif kind == "reqs":
                count = int(values.get("count", 0) or 0)
                if count:
                    row["request_count"] = count
            elif kind == "fails":
                fails = int(values.get("count", 0) or 0)
                row["fail_count"] = fails
            break
    return out


def _metrics_by_tag(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    metrics = summary.get("metrics") or {}
    tag_re = re.compile(r"^(\w+)\{[^}]*api_id:([^,}]+)")
    for key, val in metrics.items():
        if not isinstance(val, dict):
            continue
        m = tag_re.match(str(key))
        if not m:
            continue
        api_id = m.group(2).strip()
        row = out.setdefault(api_id, {"api_id": api_id})
        metric_name = m.group(1)
        values = val.get("values") or val
        if not isinstance(values, dict):
            continue
        if metric_name in ("http_req_duration", "spt_api_duration") or metric_name.startswith("spt_dur_"):
            if values.get("avg") is not None:
                row["duration_ms"] = round(float(values.get("avg") or 0), 2)
            if values.get("p(90)") is not None:
                row["duration_p90_ms"] = round(float(values.get("p(90)") or 0), 2)
            if values.get("min") is not None:
                row["duration_min_ms"] = round(float(values.get("min") or 0), 2)
            if values.get("max") is not None:
                row["duration_max_ms"] = round(float(values.get("max") or 0), 2)
        if metric_name == "http_req_failed":
            rate = float(values.get("rate", 0) or 0)
            row["error_rate"] = round(rate * 100, 2)
        if metric_name in ("http_reqs", "spt_api_reqs") or metric_name.startswith("spt_reqs_"):
            count = int(values.get("count", 0) or 0)
            if count:
                row["request_count"] = count
        if metric_name == "spt_api_fails" or metric_name.startswith("spt_fails_"):
            fails = int(values.get("count", 0) or 0)
            row["fail_count"] = fails
    return out


def build_api_index(
    traces: list[dict[str, Any]],
    summary: dict[str, Any] | None,
    apis: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    trace_by_api: dict[str, dict[str, Any]] = {}
    for t in traces:
        aid = str(t.get("api_id", ""))
        if aid:
            # Prefer a failed sample when present; else keep first
            prev = trace_by_api.get(aid)
            if prev is None or (prev.get("checks_passed") and not t.get("checks_passed")):
                trace_by_api[aid] = t

    group_stats = _group_metrics(summary or {})
    tag_stats = _metrics_by_tag(summary or {})
    named_stats = _metrics_by_api_name(summary or {})

    for api in apis:
        aid = str(api.get("id", ""))
        safe = _safe_metric_id(aid)
        row: dict[str, Any] = {
            "api_id": aid,
            "name": api.get("name", aid),
            "method": api.get("method", "GET"),
            "path": api.get("path", ""),
            "trace_available": aid in trace_by_api,
        }
        if aid in group_stats:
            gs = group_stats[aid]
            for k, v in gs.items():
                if k == "api_id":
                    continue
                if v is not None:
                    row[k] = v
        if aid in tag_stats:
            ts = tag_stats[aid]
            for k, v in ts.items():
                if k == "api_id":
                    continue
                if v is not None:
                    if k in ("duration_ms", "duration_p90_ms") and float(v or 0) == 0 and row.get(k):
                        continue
                    row[k] = v
        if safe in named_stats:
            ns = named_stats[safe]
            for k, v in ns.items():
                if k.startswith("_"):
                    continue
                if v is not None:
                    row[k] = v
        if aid in trace_by_api:
            tr = trace_by_api[aid]
            row.setdefault("status", (tr.get("response") or {}).get("status"))
            if row.get("request_count") is None and row.get("pass_count") is None:
                row["request_count"] = 1
                row["pass_count"] = 1 if tr.get("checks_passed") else 0
                row["fail_count"] = 0 if tr.get("checks_passed") else 1
                row["checks_passed"] = tr.get("checks_passed", False)
                row.setdefault("duration_ms", (tr.get("timings") or {}).get("duration_ms"))
                row.setdefault("error_rate", 0.0 if row.get("checks_passed") else 100.0)
            else:
                row.setdefault("status", (tr.get("response") or {}).get("status"))
        # Normalize count fields for the UI table
        pc = int(row.get("pass_count") or row.get("check_passes") or 0)
        fc = int(row.get("fail_count") or row.get("check_fails") or 0)
        if row.get("request_count") is None and (pc or fc):
            row["request_count"] = pc + fc
        if row.get("pass_count") is None and row.get("check_passes") is not None:
            row["pass_count"] = pc
        if row.get("fail_count") is None and row.get("check_fails") is not None:
            row["fail_count"] = fc
        if row.get("pass_count") is None and row.get("request_count") is not None:
            row["pass_count"] = max(0, int(row["request_count"]) - fc)
            row["fail_count"] = fc
        # HTTP status fallback from pass/fail when gauge/sample missing
        if row.get("status") is None:
            if pc and not fc:
                row["status"] = 200
            elif fc and not pc:
                row["status"] = "err"
        if "checks_passed" not in row:
            row["checks_passed"] = int(row.get("fail_count") or 0) == 0 and int(row.get("request_count") or 0) > 0
        by_id[aid] = row

    for aid, tr in trace_by_api.items():
        if aid not in by_id:
            by_id[aid] = {
                "api_id": aid,
                "name": tr.get("name", aid),
                "method": tr.get("method"),
                "path": "",
                "trace_available": True,
                "status": tr.get("response", {}).get("status"),
                "checks_passed": tr.get("checks_passed"),
                "duration_ms": (tr.get("timings") or {}).get("duration_ms"),
                "request_count": 1,
                "pass_count": 1 if tr.get("checks_passed") else 0,
                "fail_count": 0 if tr.get("checks_passed") else 1,
            }

    order = [str(a.get("id")) for a in apis]
    ordered = [by_id[i] for i in order if i in by_id]
    for aid, row in by_id.items():
        if aid not in order:
            ordered.append(row)
    return ordered


def load_traces_file(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def load_summary_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def save_api_index(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")


def save_traces_file(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")


def _checks_passed(status: int, checks: list[str] | None) -> bool:
    rules = checks or ["status_2xx"]
    for rule in rules:
        if rule == "status_2xx":
            if not (200 <= status < 300):
                return False
        elif rule == "status_3xx":
            if not (300 <= status < 400):
                return False
        elif rule.startswith("status_"):
            suffix = rule.replace("status_", "", 1)
            if not suffix.isdigit():
                continue
            if status != int(suffix):
                return False
    return True


async def capture_traces_http(
    base_url: str,
    apis: list[dict[str, Any]],
    *,
    body_max: int = 8000,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Fetch each API once after k6 to store request/response traces (debug profile)."""
    import time

    import httpx

    traces: list[dict[str, Any]] = []
    root = base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=timeout) as client:
        for api in apis:
            aid = str(api.get("id", ""))
            path = str(api.get("path", "/"))
            url = root + path
            params = api.get("query") or {}
            headers = dict(api.get("headers") or {})
            method = str(api.get("method", "GET")).upper()
            body = api.get("body")
            start = time.perf_counter()
            try:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    content=body if body is not None else None,
                )
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                text = response.text
                if len(text) > body_max:
                    text = text[:body_max] + "…[truncated]"
                passed = _checks_passed(response.status_code, api.get("checks"))
                traces.append(
                    {
                        "api_id": aid,
                        "name": api.get("name", aid),
                        "method": method,
                        "url": str(response.request.url),
                        "request": {"headers": headers, "body": body},
                        "response": {
                            "status": response.status_code,
                            "headers": dict(response.headers),
                            "body": text,
                        },
                        "timings": {"duration_ms": duration_ms},
                        "checks_passed": passed,
                    }
                )
            except Exception as exc:
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                traces.append(
                    {
                        "api_id": aid,
                        "name": api.get("name", aid),
                        "method": method,
                        "url": url,
                        "request": {"headers": headers, "body": body},
                        "response": {"status": 0, "headers": {}, "body": str(exc)},
                        "timings": {"duration_ms": duration_ms},
                        "checks_passed": False,
                    }
                )
    return traces


def filter_api_index(
    rows: list[dict[str, Any]],
    *,
    failed_only: bool = False,
    q: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    out = rows
    if failed_only:
        out = [r for r in out if not r.get("checks_passed")]
    if q:
        ql = q.lower()
        out = [
            r
            for r in out
            if ql in " ".join(str(r.get(k, "")) for k in ("api_id", "name", "path", "method")).lower()
        ]
    total = len(out)
    return out[offset : offset + limit], total
