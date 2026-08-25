"""
shared/tools/compressor.py — ToolResultCompressor.
Trims large MCP observations before sending to LLM to reduce token cost.
"""
from __future__ import annotations
import json, logging
from shared.core.config import settings

logger = logging.getLogger(__name__)

def compress(tool_name: str, raw: str, max_chars: int | None = None) -> str:
    """
    Compress a tool result string:
    - For list-like JSON: cap rows + compact serialization.
    - For dict JSON: compact + truncate.
    - For plain text: truncate.

    Logs token savings at DEBUG level.
    """
    max_c = max_chars if max_chars is not None else settings.AI_TOOL_RESULT_MAX_CHARS
    max_r = settings.AI_TOOL_RESULT_MAX_ROWS
    before = len(raw)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Plain text — just truncate
        result = raw[:max_c]
        _log(tool_name, before, len(result))
        return result

    # Find the list to cap
    target_list = None
    list_key = None
    if isinstance(data, list):
        target_list = data
    elif isinstance(data, dict):
        for key in ("data", "holdings", "items", "results", "list", "records"):
            if isinstance(data.get(key), list):
                target_list = data[key]
                list_key = key
                break

    if target_list is not None and len(target_list) > max_r:
        capped = target_list[:max_r]
        if list_key:
            data = {**data, list_key: capped}
        else:
            data = capped

    # Compact serialization (no whitespace)
    compact = json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    # Final char cap
    result = compact[:max_c]
    _log(tool_name, before, len(result))
    return result


def _log(tool_name: str, before: int, after: int) -> None:
    if before > 0:
        saved = round((1 - after / before) * 100, 1)
        logger.debug("compressor: tool=%s before=%d after=%d saved=%s%%", tool_name, before, after, saved)
