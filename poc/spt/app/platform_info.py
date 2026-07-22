from __future__ import annotations

PLATFORM_INFO = {
    "phase": "0 — POC",
    "this_ui": {
        "role": "Control panel — trigger tests, preview scripts, sample MCP payloads",
        "not_included": [
            "Live bench charts (throughput, latency percentiles, error breakdown)",
            "Historical run comparison",
            "Virtual User tree editor",
            "Recording import UI",
        ],
    },
    "payloads": {
        "sample_in_ui": "Tabs Payload · k6/playwright/bench/HAR show JSON sent to OctoPerf MCP import/run",
        "canonical_store": "OctoPerf — Virtual Users, scenarios, HAR/JMX/k6/Playwright after import",
        "future": "MinIO via document.* capability (Phase 1+)",
    },
    "metrics": {
        "full_details_in": "OctoPerf web UI (bench reports) or MCP analyze/report tools",
        "includes": [
            "Throughput (req/s)",
            "Error rate %",
            "Response time avg/p90/p99",
            "Per-request/action breakdown",
            "Playwright UX probe timings",
            "Trend reports",
        ],
        "this_ui_shows": "Smoke test JSON summary only (after MCP auth works)",
    },
    "providers": [
        {
            "name": "OctoPerf",
            "status": "primary — Phase 0",
            "supports": ["k6", "Playwright", "HAR", "JMX", "Postman", "MCP SDK", "self-hosted Enterprise"],
            "ui_url": "https://app.octoperf.com",
            "mcp_url": "https://api.octoperf.com/mcp",
            "metrics_ui": "OctoPerf → Project → Bench report (charts, tables, export PDF)",
        },
        {
            "name": "BlazeMeter",
            "status": "optional — Phase 3",
            "supports": ["k6", "Taurus YAML", "JMeter", "Playwright via Taurus", "MCP server"],
            "ui_url": "https://auth.blazemeter.com",
            "metrics_ui": "BlazeMeter test report dashboard",
        },
        {
            "name": "am-spt-poc (this app)",
            "status": "orchestrator only",
            "supports": ["Script preview", "MCP trigger", "Sample payloads", "Smoke orchestration"],
            "ui_url": "/spt-poc/ui",
            "metrics_ui": "Results tab — raw JSON from last run",
        },
    ],
    "next_steps": [
        "Set OCTOPERF_MCP_TOKEN + workspace/project IDs on the pod",
        "Run smoke — imports scripts to OctoPerf and starts a bench",
        "Open OctoPerf UI for full metrics, payloads used, and report drill-down",
        "Phase 1: embed OctoPerf report widgets here via MCP",
    ],
}
