import json

import pytest

from app.models.stream_events import sse_line, stage_event


def test_sse_line_format():
    line = sse_line(event="done", data={"response": {"backend": "kafka"}})
    assert line.startswith("data: ")
    assert line.endswith("\n\n")
    payload = json.loads(line[6:].strip())
    assert payload["event"] == "done"
    assert payload["response"]["backend"] == "kafka"


def test_stage_event():
    line = stage_event("parse_intent", "completed", data={"backend": "vault"}, ms=12)
    payload = json.loads(line[6:].strip())
    assert payload["event"] == "stage"
    assert payload["stage"] == "parse_intent"
    assert payload["status"] == "completed"
    assert payload["ms"] == 12
