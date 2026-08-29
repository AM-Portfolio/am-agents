from shared.formatters.user_response import sanitize_user_response


def test_sanitize_passes_normal_text():
    text = "Your portfolio is worth **₹1,25,000** with 3 holdings."
    assert sanitize_user_response(text) == text


def test_sanitize_strips_chain_of_thought():
    raw = """Thought: user wants summary
Action: call get_portfolio_summary
Execution: done
Status: FAIL
Analysis: timed out
Response draft: I couldn't load your portfolio right now. Please try again."""
    out = sanitize_user_response(raw)
    assert "Thought:" not in out
    assert "Please try again" in out


def test_sanitize_timeout_fallback():
    raw = """Thought: x
Action: y
Status: FAIL
Reason: The 'get_portfolio_summary' tool timed out after 3.0 seconds."""
    out = sanitize_user_response(raw)
    assert "timed out" in out.lower()
    assert "Thought" not in out
