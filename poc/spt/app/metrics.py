from __future__ import annotations

from typing import Any


def extract_metrics_summary(report: Any) -> dict[str, Any]:
    """Pull common bench metrics from OctoPerf MCP report payload."""
    summary: dict[str, Any] = {}

    def walk(node: Any, path: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                lk = k.lower()
                full = f"{path}.{k}" if path else k
                if lk in {
                    "throughput",
                    "hitspersecond",
                    "requestspersecond",
                    "reqps",
                    "errorrate",
                    "errors",
                    "errrate",
                    "avg",
                    "mean",
                    "min",
                    "max",
                    "p50",
                    "p90",
                    "p95",
                    "p99",
                    "median",
                    "percentile90",
                    "percentile99",
                }:
                    if isinstance(v, (int, float, str)):
                        summary[full] = v
                if lk in {"status", "state", "runstatus", "benchstatus"} and isinstance(v, str):
                    summary["status"] = v
                walk(v, full)
        elif isinstance(node, list):
            for i, item in enumerate(node[:20]):
                walk(item, f"{path}[{i}]")

    walk(report)
    if not summary and isinstance(report, dict):
        summary["raw_keys"] = list(report.keys())[:30]
    return summary
