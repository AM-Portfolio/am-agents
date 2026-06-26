from __future__ import annotations

from app.models.intent import IntentDocument, SafetyError

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


def validate(intent: IntentDocument, *, request_read_only: bool) -> None:
    if not request_read_only and intent.read_only is False:
        raise SafetyError("Writes are not supported for redis")
    if request_read_only:
        cmd = str(intent.params.get("command", intent.params.get("cmd", ""))).upper()
        if cmd and cmd in REDIS_DANGEROUS:
            raise SafetyError(f"Redis command '{cmd}' is blocked in read-only mode")


def validate_tool_params(operation: str, params: dict) -> None:
    if operation == "get" and not params.get("key"):
        raise ValueError("key required for redis.get (use entity+id or resolved key)")
    if operation == "type" and not params.get("key"):
        raise ValueError("key required for redis.type")
    if operation == "scan_keys" and not params.get("pattern"):
        raise ValueError("pattern required for redis.scan_keys")
