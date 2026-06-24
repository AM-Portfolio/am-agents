from app.agent.planner import _parse_steps, default_smoke_steps


def test_default_smoke_steps():
    steps = default_smoke_steps("https://example.com")
    assert steps[0]["action"] == "navigate"
    assert steps[0]["url"] == "https://example.com"
    assert any(s["action"] == "assert_title_not_empty" for s in steps)


def test_parse_steps_json_array():
    raw = '[{"action":"navigate","url":"https://a.com"},{"action":"wait","ms":500}]'
    steps = _parse_steps(raw)
    assert len(steps) == 2
    assert steps[1]["ms"] == 500


def test_parse_steps_strips_markdown_fence():
    raw = '```json\n[{"action":"screenshot"}]\n```'
    steps = _parse_steps(raw)
    assert steps[0]["action"] == "screenshot"
