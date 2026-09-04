"""Strip model chain-of-thought / draft labels from user-facing chat text."""
from __future__ import annotations

import re

_COT_LABEL = re.compile(
    r"^\s*(Thought|Action|Execution|Status|Analysis|Plan|Response\s+draft)\s*:",
    re.IGNORECASE | re.MULTILINE,
)
_LEAKED_TOOL_CALL = re.compile(
    r"<tool_call>.*?</tool_call>|<function=[a-zA-Z_][a-zA-Z0-9_]*>",
    re.DOTALL | re.IGNORECASE,
)
_LEAKED_MARKDOWN_TOOL_JSON = re.compile(
    r"```(?:json)?\s*\{[^`]*\"(?:tool|name|function)\"\s*:\s*\"[a-zA-Z_][a-zA-Z0-9_]*\"",
    re.DOTALL | re.IGNORECASE,
)
_LEAKED_INLINE_TOOL_JSON = re.compile(
    r"\{\s*\"(?:tool|name|function)\"\s*:\s*\"[a-zA-Z_][a-zA-Z0-9_]*\"",
    re.IGNORECASE,
)
_RESPONSE_DRAFT = re.compile(
    r"(?:\*\*)?Response\s+draft(?:\*\*)?\s*:?\s*",
    re.IGNORECASE,
)


def _looks_like_chain_of_thought(text: str) -> bool:
    if not text:
        return False
    labels = _COT_LABEL.findall(text)
    return len(labels) >= 2 or (
        len(labels) >= 1 and len(text) > 400
    )


def _extract_final_draft(text: str) -> str | None:
    parts = _RESPONSE_DRAFT.split(text)
    if len(parts) < 2:
        return None
    tail = parts[-1].strip()
    # Drop trailing meta lines the model sometimes adds after the draft.
    tail = re.split(r"\n\s*(Thought|Action|Plan)\s*:", tail, maxsplit=1, flags=re.IGNORECASE)[0]
    return tail.strip() or None


def sanitize_user_response(text: str) -> str:
    """
    Return a clean user-facing answer.

    Reasoning models and over-detailed system prompts sometimes emit
    Thought/Action/Status blocks — never show those in the UI.
    """
    if not text:
        return text

    cleaned = text.strip()
    if _LEAKED_TOOL_CALL.search(cleaned):
        return (
            "I'm working on fetching that information — please try your question again "
            "in a moment."
        )
    if _LEAKED_MARKDOWN_TOOL_JSON.search(cleaned) or _LEAKED_INLINE_TOOL_JSON.search(cleaned):
        return (
            "I'm working on fetching that information — please try your question again "
            "in a moment."
        )
    if not _looks_like_chain_of_thought(cleaned):
        return cleaned

    draft = _extract_final_draft(cleaned)
    if draft and len(draft) >= 20:
        return draft

    # Timeout / tool failure boilerplate — collapse to a short message.
    if "timed out" in cleaned.lower() and "get_portfolio_summary" in cleaned.lower():
        return (
            "I couldn't load your portfolio summary right now — the request timed out. "
            "Please try again in a moment."
        )

    if "**Status: FAIL**" in cleaned or "**Status: FAIL**".lower() in cleaned.lower():
        match = re.search(
            r"(?:Reason|reason)\**\s*:?\s*(.+?)(?:\n\n|\Z)",
            cleaned,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            reason = match.group(1).strip().strip("*")
            if reason:
                return f"I couldn't complete that request: {reason}"

    # Last resort: first substantial paragraph without COT labels.
    for block in re.split(r"\n\s*\n", cleaned):
        block = block.strip()
        if not block or _COT_LABEL.match(block):
            continue
        if len(block) >= 40:
            return block

    return "I couldn't complete that request. Please try again."
