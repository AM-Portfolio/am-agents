from __future__ import annotations

from typing import Literal

ErrorClass = Literal["retryable", "fatal", "policy_denied"]


class CapabilityError(Exception):
    def __init__(self, message: str, *, error_class: ErrorClass = "fatal") -> None:
        super().__init__(message)
        self.message = message
        self.error_class = error_class


def classify_error(exc: BaseException) -> ErrorClass:
    if isinstance(exc, CapabilityError):
        return exc.error_class
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timeout" in text or "temporarily" in text or "429" in text or "503" in text:
        return "retryable"
    if "denied" in text or "forbidden" in text or "policy" in text or "blocked" in text:
        return "policy_denied"
    return "fatal"
