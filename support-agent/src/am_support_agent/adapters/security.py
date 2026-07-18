"""Security boundary stubs — fail-closed for live side effects."""

from __future__ import annotations

import os
import re
from typing import Any


_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+"
)


class Redactor:
    name = "redactor"

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "wired": True}

    def redact_text(self, text: str) -> str:
        return _SECRET_RE.sub(r"\1=[REDACTED]", text or "")

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in data.items():
            key = str(k).lower()
            if any(s in key for s in ("token", "secret", "password", "api_key", "authorization")):
                out[k] = "[REDACTED]"
            elif isinstance(v, dict):
                out[k] = self.redact_dict(v)
            elif isinstance(v, str):
                out[k] = self.redact_text(v)
            else:
                out[k] = v
        return out


class SecretBroker:
    """Env-backed secret lookup — not a vault client yet."""

    name = "env-secrets"

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "wired": True,
            "note": "reads process env only; replace with vault before prod side effects",
        }

    def get(self, ref: str) -> str | None:
        return os.getenv(ref) or os.getenv(ref.upper()) or None


class SandboxPolicy:
    name = "sandbox"

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "wired": True}

    def allow_spt(self, *, sandbox: bool) -> tuple[bool, str]:
        if sandbox:
            return True, "sandbox"
        if os.getenv("SUPPORT_AGENT_ALLOW_UNSANDBOXED_SPT", "").lower() in {"1", "true", "yes"}:
            return True, "unsandboxed_override"
        return False, "SPT requires sandbox=true (fail-closed)"
