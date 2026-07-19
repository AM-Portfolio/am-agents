"""Dedicated A2A Postgres schema for support-agent (not legacy agent_runs).

Canonical migrations live in `stores/migrations.py`. This module re-exports
symbols for backward compatibility with PostgresTaskRunStore and tests.
"""

from __future__ import annotations

from am_support_agent.stores.migrations import (
    A2A_POSTGRES_TABLE,
    EPISODE_POSTGRES_TABLE,
    FEEDBACK_POSTGRES_TABLE,
    LEGACY_RUNSTORE_TABLES,
    SUPPORT_AGENT_SCHEMA_SQL,
    apply_migrations,
)

__all__ = [
    "A2A_POSTGRES_TABLE",
    "EPISODE_POSTGRES_TABLE",
    "FEEDBACK_POSTGRES_TABLE",
    "LEGACY_RUNSTORE_TABLES",
    "SUPPORT_AGENT_SCHEMA_SQL",
    "apply_migrations",
]
