"""Shared enums and opaque-ref helpers."""

from enum import Enum


class RunKind(str, Enum):
    ALERT_INCIDENT = "alert_incident"
    SPT = "spt"
    VERIFY = "verify"
    HANDOFF = "handoff"


class RunStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    RUNNING = "running"
    PASSED = "passed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_HUMAN = "needs_human"


class StepStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class FailureMode(str, Enum):
    CONTINUE = "continue"
    FAIL_FAST = "fail_fast"


class ErrorClass(str, Enum):
    RETRYABLE = "retryable"
    FATAL = "fatal"
    POLICY_DENIED = "policy_denied"
