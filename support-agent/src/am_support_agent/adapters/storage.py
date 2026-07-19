"""Storage facades — A2A TaskRunStore + DocStore prefix boundary.

Does not wire legacy `libs/platform-adapters` PostgresRunStore (agent_runs).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_DOC_PREFIX = "support-agent-v2/"


@dataclass(frozen=True)
class DocStoreNamespace:
    """Distinct MinIO/object prefix for parallel v2 artifacts."""

    bucket_env: str = "SUPPORT_AGENT_DOC_BUCKET"
    prefix_env: str = "SUPPORT_AGENT_DOC_PREFIX"
    default_prefix: str = DEFAULT_DOC_PREFIX

    def bucket(self) -> str | None:
        value = os.getenv(self.bucket_env, "").strip()
        return value or None

    def prefix(self) -> str:
        raw = os.getenv(self.prefix_env, self.default_prefix).strip()
        if not raw.endswith("/"):
            raw = f"{raw}/"
        if raw in {"/", "agent-platform/", "agent_runs/"}:
            raise ValueError(
                f"refusing DocStore prefix {raw!r}; use a distinct "
                f"support-agent-v2 prefix"
            )
        return raw

    def object_key(self, relative: str) -> str:
        rel = relative.lstrip("/")
        return f"{self.prefix()}{rel}"

    def status(self) -> dict[str, object]:
        return {
            "bucket": self.bucket(),
            "prefix": self.prefix(),
            "wired": False,
            "note": (
                "Use composition.build_runtime() DocumentStore (memory/minio); "
                "namespace helpers ensure v2 artifacts never collide with legacy prefixes."
            ),
        }


def legacy_postgres_runstore_compatible() -> bool:
    """False — platform-adapters AgentRun ledger ≠ A2A TaskRunStore."""
    return False


__all__ = [
    "DEFAULT_DOC_PREFIX",
    "DocStoreNamespace",
    "legacy_postgres_runstore_compatible",
]
