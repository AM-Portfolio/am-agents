"""Alert Ops ingest enrichment — import temporal_client via path."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4] / "am-obs-platform" / "apps" / "alerting-runtime" / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alerting_runtime.relay.temporal_client import _alert_dict_from_payload  # noqa: E402


def test_alert_dict_keeps_evidence_and_trace() -> None:
    payload = {
        "status": "firing",
        "alerts": [
            {
                "fingerprint": "fp1",
                "startsAt": "2026-07-18T00:00:00Z",
                "generatorURL": "http://grafana/d/x",
                "valueString": "val=1",
                "labels": {
                    "alertname": "HighError",
                    "severity": "critical",
                    "team": "payments",
                    "trace_id": "abc123",
                    "span_id": "def456",
                },
                "annotations": {"summary": "error rate high", "runbook": "http://rb"},
            },
            {"labels": {"alertname": "Other"}},
        ],
    }
    alert = _alert_dict_from_payload(payload)
    assert alert["priority"] == "P1"
    assert alert["fingerprint"] == "fp1"
    assert alert["generator_url"] == "http://grafana/d/x"
    assert alert["annotations"]["runbook"] == "http://rb"
    assert alert["group_size"] == 2
    assert alert["sibling_alertnames"] == ["Other"]
    assert alert["trace_id"] == "abc123"
    assert alert["span_id"] == "def456"
