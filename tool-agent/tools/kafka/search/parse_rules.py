from __future__ import annotations

import re
from typing import Any

from app.models.intent import IntentDocument
from tools.kafka.search.convention import extract_topic


def parse_rules(query: str, *, tool_name: str) -> IntentDocument | None:
    q = query.lower()
    if not (tool_name == "kafka" or "kafka" in q):
        return None

    topic = extract_topic(query)
    wants_lag = any(w in q for w in ("lag", "consumer group", "consumer_group"))
    wants_messages = any(
        w in q
        for w in (
            "message",
            "messages",
            "peek",
            "read",
            "published",
            "publish",
            "last",
            "recent",
            "latest",
        )
    )
    wants_describe = topic and any(w in q for w in ("describe", "metadata", "partitions", "partition"))

    if wants_lag:
        params: dict[str, Any] = {}
        if topic:
            params["topic"] = topic
        group_match = re.search(r"(?:group|consumer group)\s+([\w.-]+)", q)
        if group_match:
            params["group"] = group_match.group(1)
        return IntentDocument(
            backend=tool_name,
            operation="consumer_lag",
            params=params,
            confidence=0.75,
            rationale="Rule: kafka consumer lag",
        )

    if wants_messages:
        if not topic:
            return None
        limit = 1 if any(w in q for w in ("last", "latest", "most recent")) else 10
        return IntentDocument(
            backend=tool_name,
            operation="peek_messages",
            params={"topic": topic, "limit": limit, "from_tail": True},
            confidence=0.85,
            rationale="Rule: kafka peek messages",
        )

    if wants_describe and topic:
        return IntentDocument(
            backend=tool_name,
            operation="describe_topic",
            params={"topic": topic},
            confidence=0.8,
            rationale="Rule: kafka describe topic",
        )

    if topic and not wants_messages:
        return IntentDocument(
            backend=tool_name,
            operation="describe_topic",
            params={"topic": topic},
            confidence=0.7,
            rationale="Rule: kafka topic name detected",
        )

    return IntentDocument(
        backend=tool_name,
        operation="list_topics",
        params={},
        confidence=0.75,
        rationale="Rule: kafka list topics",
    )
