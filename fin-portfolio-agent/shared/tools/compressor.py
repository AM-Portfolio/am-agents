"""
shared/tools/compressor.py — ToolResultCompressor.
Trims large MCP observations before sending to LLM to reduce token cost.
"""
from __future__ import annotations
import json, logging
from typing import Any
from shared.core.config import settings

logger = logging.getLogger(__name__)


def _redact_pii(obj: Any) -> Any:
    """Phase 4 Security: Scrub sensitive fields before they enter the LLM or logs."""
    if isinstance(obj, dict):
        scrubbed = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if any(sensitive in k_lower for sensitive in ["account", "email", "phone", "token", "password", "ssn"]):
                scrubbed[k] = "[REDACTED]"
            elif k_lower in ["quantity", "totalvalue", "value", "investedamount", "averagecost"]:
                # The LLM needs these for math, but we round/fuzz them slightly for privacy in logs 
                # or just pass them through if the system prompt requires exact math.
                # Per Phase 4: "Redact holdings qty/value/symbols from logs, traces..."
                # We will keep them for the LLM path here, but actual trace redaction happens in the logger.
                # Let's redact exact decimals to prevent exact value fingerprinting.
                if isinstance(v, (int, float)):
                    scrubbed[k] = round(v, 2)
                else:
                    scrubbed[k] = v
            else:
                scrubbed[k] = _redact_pii(v)
        return scrubbed
    elif isinstance(obj, list):
        return [_redact_pii(x) for x in obj]
    return obj


def _to_toon(obj: Any, indent: int = 0) -> str:
    """Recursively formats data into Token Oriented Object Notation (TOON)."""
    ind = "  " * indent
    if isinstance(obj, dict):
        if not obj: return ind + "{}"
        lines = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{ind}{k}:")
                lines.append(_to_toon(v, indent + 1))
            else:
                lines.append(f"{ind}{k}: {v}")
        return "\n".join(lines)
    elif isinstance(obj, list):
        if not obj: return ind + "[]"
        # Tabular optimization for uniform flat dicts
        if all(isinstance(x, dict) for x in obj):
            keys = []
            for x in obj:
                for k in x.keys():
                    if k not in keys: keys.append(k)
            is_flat = all(not isinstance(v, (dict, list)) for x in obj for v in x.values())
            if is_flat and 0 < len(keys) <= 12:
                header = ind + " | ".join(str(k) for k in keys)
                lines = [header]
                for x in obj:
                    lines.append(ind + " | ".join(str(x.get(k, "")) for k in keys))
                return "\n".join(lines)
        # Fallback for mixed/nested lists
        lines = []
        for x in obj:
            if isinstance(x, (dict, list)):
                lines.append(f"{ind}-")
                lines.append(_to_toon(x, indent + 1))
            else:
                lines.append(f"{ind}- {x}")
        return "\n".join(lines)
    else:
        return ind + str(obj)

def compress(tool_name: str, raw: str, max_chars: int | None = None) -> str:
    """
    Compress a tool result string into Token Oriented Object Notation (TOON):
    - Converts JSON into a hybrid YAML/Tabular format to save tokens.
    """
    max_c = max_chars if max_chars is not None else settings.AI_TOOL_RESULT_MAX_CHARS
    max_r = settings.AI_TOOL_RESULT_MAX_ROWS
    before = len(raw)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
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
            
    # Phase 4: Apply PII Guardrail before LLM observation
    data = _redact_pii(data)

    if settings.AI_OBSERVATION_FORMAT == "json":
        compact = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    else:
        # Convert to TOON format
        try:
            compact = _to_toon(data)
        except Exception as e:
            logger.error("Failed TOON conversion: %s", e)
            compact = json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    # Final char cap
    result = compact[:max_c]
    _log(tool_name, before, len(result))
    return result


def _log(tool_name: str, before: int, after: int) -> None:
    if before > 0:
        saved = round((1 - after / before) * 100, 1)
        logger.debug("compressor: tool=%s before=%d after=%d saved=%s%%", tool_name, before, after, saved)
