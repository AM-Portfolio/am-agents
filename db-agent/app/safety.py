from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.intent_schema import BACKEND_OPERATIONS, IntentDocument, SafetyError, ToolCall

SQL_WRITE_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|COPY|MERGE|REPLACE)\b",
    re.IGNORECASE,
)
SQL_MUST_BE_SELECT = re.compile(r"^\s*(SELECT|WITH|SHOW|DESCRIBE|EXPLAIN)\b", re.IGNORECASE)

REDIS_DANGEROUS = frozenset(
    {
        "FLUSHALL",
        "FLUSHDB",
        "CONFIG",
        "DEBUG",
        "SLAVEOF",
        "SHUTDOWN",
        "SAVE",
        "BGSAVE",
        "DEL",
        "SET",
        "MSET",
        "HSET",
        "LPUSH",
        "RPUSH",
        "SADD",
        "ZADD",
    }
)
QDRANT_WRITE_OPS = frozenset({"upsert", "delete", "create_collection", "delete_collection"})
KAFKA_WRITE_OPS = frozenset({"produce", "publish"})
MONGO_WRITE_KEYS = frozenset(
    {"deleteMany", "deleteOne", "insert", "insertOne", "update", "updateMany", "drop", "$out", "$merge"}
)


def validate_intent(intent: IntentDocument, *, request_read_only: bool) -> None:
    read_only = request_read_only and settings.DB_AGENT_READ_ONLY_DEFAULT
    if not read_only and not settings.DB_AGENT_ALLOW_WRITES:
        raise SafetyError("Writes are disabled (DB_AGENT_ALLOW_WRITES=false)")

    if intent.operation not in BACKEND_OPERATIONS.get(intent.backend, []):
        raise SafetyError(
            f"Unknown operation '{intent.operation}' for backend '{intent.backend}'"
        )

    if read_only:
        _enforce_read_only_intent(intent)


def validate_tool_call(tool_call: ToolCall) -> None:
    """Layer 4 — re-scan immediately before MCP/adapter execution."""
    if settings.DB_AGENT_ALLOW_WRITES and not settings.DB_AGENT_READ_ONLY_DEFAULT:
        return
    _scan_params(tool_call.backend, tool_call.operation, tool_call.params)
    if tool_call.source == "mcp" and not tool_call.read_only:
        raise SafetyError("MCP tool call is not marked read_only")


def _enforce_read_only_intent(intent: IntentDocument) -> None:
    _scan_params(intent.backend, intent.operation, intent.params)
    if intent.backend == "qdrant" and intent.operation in QDRANT_WRITE_OPS:
        raise SafetyError(f"Qdrant operation '{intent.operation}' is blocked in read-only mode")
    if intent.backend == "kafka" and intent.operation in KAFKA_WRITE_OPS:
        raise SafetyError(f"Kafka operation '{intent.operation}' is blocked in read-only mode")
    if not intent.read_only:
        raise SafetyError("Intent marked read_only=false but request requires read-only")


def _scan_params(backend: str, operation: str, params: dict[str, Any]) -> None:
    if backend in ("postgres", "influx") or operation in ("run_sql", "query_flux", "query_influxql"):
        for key in ("sql", "query", "statement", "flux", "influxql"):
            if key in params:
                _validate_sqlish(str(params[key]))

    if backend == "mongodb" or operation in ("find", "aggregate"):
        _validate_mongo_params(params)

    if backend == "redis":
        cmd = str(params.get("command", params.get("cmd", ""))).upper()
        if cmd and cmd in REDIS_DANGEROUS:
            raise SafetyError(f"Redis command '{cmd}' is blocked in read-only mode")

    _scan_nested_strings(params)


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


def _validate_mongo_params(params: dict[str, Any]) -> None:
    blob = json.dumps(params, default=str).lower()
    for key in MONGO_WRITE_KEYS:
        if key.lower() in blob:
            raise SafetyError(f"Mongo write operation '{key}' is blocked in read-only mode")


def _scan_nested_strings(params: dict[str, Any]) -> None:
    for value in params.values():
        if isinstance(value, str):
            upper = value.upper()
            if any(kw in upper for kw in ("DROP TABLE", "DELETE FROM", "TRUNCATE ")):
                raise SafetyError("Destructive SQL pattern detected in tool parameters")


def cap_rows(data: object, max_rows: int) -> tuple[object, list[str]]:
    warnings: list[str] = []
    if isinstance(data, list) and len(data) > max_rows:
        warnings.append(f"Truncated results to {max_rows} rows (was {len(data)})")
        return data[:max_rows], warnings
    if isinstance(data, dict):
        for key in ("rows", "items", "keys", "collections", "topics", "results"):
            val = data.get(key)
            if isinstance(val, list) and len(val) > max_rows:
                trimmed = dict(data)
                trimmed[key] = val[:max_rows]
                warnings.append(f"Truncated '{key}' to {max_rows} items (was {len(val)})")
                return trimmed, warnings
    return data, warnings
