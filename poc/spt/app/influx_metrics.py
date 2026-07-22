"""InfluxDB v2 line-protocol helpers for SPT run summaries."""

from __future__ import annotations

import re
from typing import Any


_TAG_BAD = re.compile(r"[, =]")


def influx_tag(value: Any, *, default: str = "unknown") -> str:
    """Escape Influx line-protocol tag values (spaces, commas, equals)."""
    raw = str(value if value is not None and value != "" else default)
    return _TAG_BAD.sub("_", raw).replace("\\", "_")[:128]


def influx_num(value: Any, *, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_spt_influx_lines(
    *,
    run_id: str,
    config: dict[str, Any],
    metrics: dict[str, Any] | None,
    api_summary: list[dict[str, Any]] | None,
    status: str,
    duration_s: float | None = None,
) -> list[str]:
    """Build spt_run + spt_api (+ legacy) line protocol lines."""
    metrics = metrics or {}
    service = influx_tag(config.get("service"), default="unknown")
    environment = influx_tag(config.get("environment"), default="dev")
    profile = influx_tag(config.get("run_profile") or "load", default="load")
    run_name = influx_tag(
        config.get("name") or config.get("config_name") or config.get("run_name"),
        default="unnamed",
    )
    rid = influx_tag(run_id)
    st = influx_tag(status, default="unknown")

    bench = (config.get("payloads") or {}).get("bench_run") or {}
    vus = influx_num(bench.get("vus"))
    iterations = influx_num(bench.get("iterations"))

    rps = influx_num(
        metrics.get("throughput.requestsPerSecond")
        or metrics.get("http_reqs.rate")
        or metrics.get("rps")
    )
    p50 = influx_num(metrics.get("responseTime.p50") or metrics.get("responseTime.med"))
    p90 = influx_num(metrics.get("responseTime.p90"))
    p95 = influx_num(metrics.get("responseTime.p95"))
    p99 = influx_num(metrics.get("responseTime.p99"))
    error_rate = influx_num(metrics.get("errorRate") or metrics.get("http_req_failed.rate"))

    rows = api_summary or []
    api_pass = sum(1 for a in rows if a.get("checks_passed") is True)
    api_fail = sum(1 for a in rows if a.get("checks_passed") is False)
    api_count = len(rows) or influx_num(None)  # 0 if empty

    # Prefer explicit counts on the result if present in metrics
    if metrics.get("api_pass_count") is not None:
        api_pass = int(influx_num(metrics.get("api_pass_count")))
    if metrics.get("api_fail_count") is not None:
        api_fail = int(influx_num(metrics.get("api_fail_count")))

    dur = influx_num(duration_s)

    lines: list[str] = [
        (
            f"spt_run,service={service},environment={environment},run_id={rid},"
            f"run_name={run_name},profile={profile},status={st} "
            f"rps={rps},p50={p50},p90={p90},p95={p95},p99={p99},"
            f"error_rate={error_rate},vus={vus},iterations={iterations},"
            f"api_pass={api_pass},api_fail={api_fail},api_count={api_count},duration_s={dur}"
        ),
        # Legacy compat (one release)
        (
            f"k6_run,service={service},run_id={rid},run_name={run_name} "
            f"rps={rps},p90={p90},error_rate={error_rate}"
        ),
    ]

    for row in rows:
        aid = influx_tag(row.get("api_id") or row.get("id"), default="unknown")
        method = influx_tag(row.get("method") or "GET", default="GET")
        requests = influx_num(
            row.get("request_count")
            if row.get("request_count") is not None
            else (row.get("pass_count") or 0) + (row.get("fail_count") or 0)
        )
        pass_n = influx_num(row.get("pass_count") or row.get("check_passes"))
        fail_n = influx_num(row.get("fail_count") or row.get("check_fails"))
        if row.get("checks_passed") is False and fail_n == 0:
            fail_n = 1.0
        if row.get("checks_passed") is True and pass_n == 0 and requests == 0:
            pass_n = 1.0
        avg_ms = influx_num(row.get("duration_ms"))
        p90_ms = influx_num(row.get("duration_p90_ms") or row.get("duration_ms"))
        p95_ms = influx_num(row.get("duration_p95_ms") or row.get("duration_p90_ms"))
        row_err = influx_num(row.get("error_rate"))
        if row_err == 0 and requests > 0 and fail_n > 0:
            row_err = round(100.0 * fail_n / requests, 2)
        http_status = influx_num(row.get("status") if isinstance(row.get("status"), (int, float)) else 0)

        lines.append(
            (
                f"spt_api,service={service},environment={environment},run_id={rid},"
                f"run_name={run_name},api_id={aid},method={method} "
                f"requests={requests},pass={pass_n},fail={fail_n},"
                f"avg_ms={avg_ms},p90_ms={p90_ms},p95_ms={p95_ms},"
                f"error_rate={row_err},http_status={http_status}"
            )
        )
        lines.append(
            (
                f"http_req_duration,service={service},run_id={rid},api_id={aid} "
                f"p90={p90_ms},error_rate={row_err}"
            )
        )

    return lines
