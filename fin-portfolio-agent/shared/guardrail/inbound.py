"""
shared/guardrail/inbound.py — Inbound GuardRail.
Blocks prompt injection, credential exfil, and PII fishing before LLM call.
"""
from __future__ import annotations
import logging, re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class GuardRailResult:
    blocked: bool
    reason: str | None = None

# Patterns — case-insensitive substring match
_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore your instructions",
    "you are now",
    "forget your instructions",
    "jailbreak",
    "act as",
    "pretend you are",
    "disregard",
    "\nsystem:",
    "[system]",
]

_CREDENTIAL_PATTERNS = [
    "api key",
    "secret key",
    "api secret",
    "private key",
    "auth token",
    "access token",
    "bearer token",
    "password",
    "credentials",
]

_PII_PATTERNS = [
    "send email",
    "send sms",
    "share my data",
    "export my data",
    "send to",
    "forward to",
    "leak",
]


def check_inbound(message: str, user_id: str, trace_id: str) -> GuardRailResult:
    """
    Check a user message before sending to LLM.
    Returns GuardRailResult(blocked=True, reason=...) if suspicious.
    No PII logged — only trace_id and category.
    """
    lower = message.lower()

    for pattern in _INJECTION_PATTERNS:
        if pattern in lower:
            logger.warning("guardrail: BLOCKED injection trace_id=%s category=prompt_injection", trace_id)
            return GuardRailResult(blocked=True, reason="Potential prompt injection detected.")

    for pattern in _CREDENTIAL_PATTERNS:
        if pattern in lower:
            logger.warning("guardrail: BLOCKED credential_exfil trace_id=%s", trace_id)
            return GuardRailResult(blocked=True, reason="Requests for credentials or keys are not permitted.")

    for pattern in _PII_PATTERNS:
        if pattern in lower:
            logger.warning("guardrail: BLOCKED pii_fishing trace_id=%s", trace_id)
            return GuardRailResult(blocked=True, reason="Data sharing requests are not permitted.")

    return GuardRailResult(blocked=False)
