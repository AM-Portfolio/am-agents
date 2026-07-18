"""Shared helpers — OTel/HTTP stubs (Phase 0b)."""

__version__ = "0.1.0"

from agent_common.dotenv import load_dotenv

__all__ = ["load_dotenv", "redact_headers"]


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    out = dict(headers)
    for key in list(out):
        if key.lower() in {"authorization", "x-api-key", "cookie"}:
            out[key] = "***"
    return out
