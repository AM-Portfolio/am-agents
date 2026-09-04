"""Per-turn token budget for fin-agent chat."""
from shared.agents.token_budget import (
    TokenBudgetExceededError,
    assert_within_budget,
    current_turn_tokens,
    record_turn_tokens,
    reset_turn_token_budget,
    token_budget_exceeded,
    turn_token_limit,
)
from shared.core.config import settings


def test_record_and_check_budget():
    reset_turn_token_budget()
    settings.AI_MAX_TOKENS_PER_TURN = 1000
    assert current_turn_tokens() == 0
    total = record_turn_tokens({"prompt_tokens": 400, "completion_tokens": 100, "total_tokens": 500})
    assert total == 500
    assert not token_budget_exceeded()
    record_turn_tokens({"total_tokens": 600})
    assert token_budget_exceeded()


def test_assert_raises_when_over_budget():
    reset_turn_token_budget()
    settings.AI_MAX_TOKENS_PER_TURN = 500
    record_turn_tokens({"total_tokens": 500})
    try:
        assert_within_budget()
        assert False, "expected TokenBudgetExceededError"
    except TokenBudgetExceededError as exc:
        assert exc.used == 500
        assert exc.limit == 500


def test_zero_limit_disables_cap():
    reset_turn_token_budget()
    settings.AI_MAX_TOKENS_PER_TURN = 0
    record_turn_tokens({"total_tokens": 999999})
    assert not token_budget_exceeded()
    assert_within_budget()


def test_turn_token_limit_reads_config():
    settings.AI_MAX_TOKENS_PER_TURN = 12000
    assert turn_token_limit() == 12000
