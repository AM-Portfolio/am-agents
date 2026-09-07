"""Per chat-turn LLM token budget (one user message → one agent run)."""
from __future__ import annotations

from typing import Any

from shared.context.request_context import chat_tokens_bag_var
from shared.core.config import settings


class TokenBudgetExceededError(Exception):
    """Raised before an LLM call when the turn token cap is already exhausted."""

    def __init__(self, used: int, limit: int) -> None:
        self.used = used
        self.limit = limit
        super().__init__(f"Token budget exceeded for this chat turn: {used}/{limit}")


def reset_turn_token_budget() -> None:
    """Bind a fresh mutable counter for this request (visible across asyncio tasks)."""
    chat_tokens_bag_var.set({"used": 0})


def _bag() -> dict:
    bag = chat_tokens_bag_var.get()
    if bag is None:
        bag = {"used": 0}
        chat_tokens_bag_var.set(bag)
    return bag


def current_turn_tokens() -> int:
    return int(_bag().get("used") or 0)


def _usage_total(usage: dict[str, Any] | None) -> int:
    if not usage:
        return 0
    total = int(usage.get("total_tokens") or 0)
    if total:
        return total
    return int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)


def record_turn_tokens(usage: dict[str, Any] | None) -> int:
    """Add provider usage to the current turn total. Returns new cumulative total."""
    added = _usage_total(usage)
    bag = _bag()
    total = int(bag.get("used") or 0) + added
    bag["used"] = total
    return total


def turn_token_limit() -> int:
    return int(settings.AI_MAX_TOKENS_PER_TURN)


def token_budget_exceeded() -> bool:
    limit = turn_token_limit()
    return limit > 0 and current_turn_tokens() >= limit


def assert_within_budget() -> None:
    if token_budget_exceeded():
        raise TokenBudgetExceededError(current_turn_tokens(), turn_token_limit())
