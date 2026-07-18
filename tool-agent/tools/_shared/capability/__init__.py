"""Shared helpers for generic capability plugins."""

from tools._shared.capability.errors import CapabilityError, classify_error
from tools._shared.capability.idempotency import IdempotencyStore, get_idempotency_store
from tools._shared.capability.plan_binding import (
    clear_plan_bindings,
    intent_plan_hash,
    issue_plan_binding,
    verify_plan_binding,
)
from tools._shared.capability.provider import resolve_provider
from tools._shared.capability.results import CapabilityResult, normalize_result

__all__ = [
    "CapabilityError",
    "CapabilityResult",
    "IdempotencyStore",
    "classify_error",
    "clear_plan_bindings",
    "get_idempotency_store",
    "intent_plan_hash",
    "issue_plan_binding",
    "normalize_result",
    "resolve_provider",
    "verify_plan_binding",
]
