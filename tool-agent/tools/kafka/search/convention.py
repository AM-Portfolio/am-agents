from __future__ import annotations

import difflib
import re
from typing import Any

from app.schema.loader import get_schema_catalog

KAFKA_TOPIC_PATTERN = re.compile(r"\b([a-z][a-z0-9_-]*(?:-[a-z0-9_-]+)+)\b", re.IGNORECASE)

_TOPIC_STOPWORDS = frozenset(
    {
        "kafka",
        "topics",
        "topic",
        "cluster",
        "infra",
        "message",
        "messages",
        "read-only",
        "readonly",
        "only",
        "backend",
    }
)

_TOPIC_ALIASES: dict[str, str] = {
    "am-portfolio-events": "am-portfolio-update",
    "am-trade-executions": "am-trade-update",
    "portfolio-events": "am-portfolio-update",
    "portfolio_events": "am-portfolio-update",
    "trade-executions": "am-trade-update",
    "trade_executions": "am-trade-update",
    "am-trade": "am-trade-update",
    "am-portfolio": "am-portfolio-update",
}

_NL_TOPIC_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"portfolio\s+stream|am-portfolio-stream", re.I), "am-portfolio-stream"),
    (re.compile(r"portfolio\s+update|am-portfolio-update", re.I), "am-portfolio-update"),
    (re.compile(r"user\s+watching|am-user-watching", re.I), "am-user-watching"),
    (re.compile(r"trade\s+update|am-trade-update", re.I), "am-trade-update"),
    (re.compile(r"stock\s+price|am-stock-price-update", re.I), "am-stock-price-update"),
    (re.compile(r"holding\s+update|am-holding-update", re.I), "am-holding-update"),
    (re.compile(r"trigger\s+calculation|am-trigger-calculation", re.I), "am-trigger-calculation"),
    (re.compile(r"dashboard\s+summary|dashboard-summary-update", re.I), "dashboard-summary-update"),
    (re.compile(r"dashboard\s+movers|dashboard-movers-update", re.I), "dashboard-movers-update"),
    (re.compile(r"dashboard\s+activity|dashboard-activity-update", re.I), "dashboard-activity-update"),
    (re.compile(r"dashboard\s+allocation|dashboard-allocation-update", re.I), "dashboard-allocation-update"),
    (re.compile(r"dashboard\s+history|dashboard-history-update", re.I), "dashboard-history-update"),
]


def normalize_topic(name: str) -> str:
    catalog = get_schema_catalog()
    alias = catalog.kafka_topic_alias(name)
    if alias:
        return alias
    key = name.lower().strip()
    return _TOPIC_ALIASES.get(key, key)


def extract_topic(query: str) -> str | None:
    q = query.lower()
    for pattern, topic in _NL_TOPIC_HINTS:
        if pattern.search(query):
            return topic
    for token in re.findall(r"[\w.-]+", query):
        if token.startswith("am-") and len(token) > 3:
            return normalize_topic(token)
        if token.startswith("dashboard-") and len(token) > 12:
            return token.lower()
    for pattern in (
        r"topic[s]?\s+([a-z][\w.-]+)",
        r"on\s+([a-z][\w.-]+)\s+topic",
        r"from\s+([a-z][\w.-]+)",
    ):
        match = re.search(pattern, q)
        if match:
            candidate = match.group(1).rstrip(".,")
            if candidate not in _TOPIC_STOPWORDS:
                return normalize_topic(candidate)
    for match in KAFKA_TOPIC_PATTERN.finditer(query):
        candidate = match.group(1)
        if candidate.startswith("am-") or candidate.startswith("dashboard-"):
            return normalize_topic(candidate)
    return None


def fuzzy_topic(token: str, known: list[str], *, cutoff: float = 0.75) -> str | None:
    if not known:
        return None
    normalized = normalize_topic(token)
    if normalized in known:
        return normalized
    matches = difflib.get_close_matches(normalized, known, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def resolve_entity_topic(entity_name: str) -> str | None:
    mapping = get_schema_catalog().entity(entity_name)
    if mapping and mapping.backend == "kafka" and mapping.collection:
        return str(mapping.collection)
    return None


def resolve_topic_param(params: dict[str, Any], query: str = "") -> tuple[dict[str, Any], str | None, str]:
    """Returns (params, matched_topic, resolve_method)."""
    resolved = dict(params)
    entity = resolved.pop("entity", None)
    if entity and not resolved.get("topic"):
        topic = resolve_entity_topic(str(entity))
        if topic:
            resolved["topic"] = topic
            return resolved, topic, "entity"
    topic = resolved.get("topic")
    if topic:
        normalized = normalize_topic(str(topic))
        resolved["topic"] = normalized
        return resolved, normalized, "convention"
    if query:
        extracted = extract_topic(query)
        if extracted:
            resolved["topic"] = extracted
            return resolved, extracted, "convention"
    return resolved, None, "unknown"
