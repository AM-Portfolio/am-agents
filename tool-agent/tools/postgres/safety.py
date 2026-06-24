from __future__ import annotations

import re

from app.config import settings
from app.models.intent import IntentDocument, SafetyError

SQL_WRITE_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|COPY|MERGE|REPLACE)\b",
    re.IGNORECASE,
)
SQL_MUST_BE_SELECT = re.compile(r"^\s*(SELECT|WITH|SHOW|DESCRIBE|EXPLAIN)\b", re.IGNORECASE)


def _validate_sqlish(text: str) -> None:
    if SQL_WRITE_PATTERN.search(text):
        raise SafetyError("SQL write/destructive statements are blocked in read-only mode")
    stripped = text.strip()
    if stripped and not SQL_MUST_BE_SELECT.match(stripped):
        if any(
            kw in stripped.upper()
            for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE")
        ):
            raise SafetyError("Only read-only SQL (SELECT/WITH/SHOW/EXPLAIN) is allowed")


def validate(intent: IntentDocument, *, request_read_only: bool) -> None:
    if not request_read_only and not settings.TOOL_AGENT_ALLOW_WRITES:
        raise SafetyError("Writes are disabled (TOOL_AGENT_ALLOW_WRITES=false)")

    if request_read_only or settings.TOOL_AGENT_READ_ONLY_DEFAULT:
        if not intent.read_only:
            raise SafetyError("Intent marked read_only=false but request requires read-only")
        sql = intent.params.get("sql")
        if sql:
            _validate_sqlish(str(sql))


def validate_tool_params(operation: str, params: dict[str, object]) -> None:
    if operation == "run_sql":
        sql = params.get("sql")
        if sql:
            _validate_sqlish(str(sql))
