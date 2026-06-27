from __future__ import annotations

import asyncio
import difflib
from dataclasses import dataclass, field

from app.config import settings
from tools._shared.ttl_cache import TtlCache
from tools.kafka.search.convention import normalize_topic

_cache: TtlCache["KafkaTopicSnapshot"] | None = None


@dataclass
class KafkaTopicSnapshot:
    topics: list[str] = field(default_factory=list)
    am_topics: list[str] = field(default_factory=list)
    dashboard_topics: list[str] = field(default_factory=list)
    dlq_topics: list[str] = field(default_factory=list)


def _get_cache() -> TtlCache[KafkaTopicSnapshot]:
    global _cache
    if _cache is None:
        _cache = TtlCache(
            ttl_seconds=float(settings.KAFKA_TOPIC_CACHE_TTL_SECONDS),
            enabled=settings.KAFKA_TOPIC_CACHE_ENABLED,
        )
    return _cache


async def _refresh() -> KafkaTopicSnapshot:
    from tools.kafka.adapter import _list_topics_sync

    raw = await asyncio.to_thread(_list_topics_sync, max_rows=500)
    names = [str(item.get("name", "")) for item in raw.get("topics") or [] if item.get("name")]
    snapshot = KafkaTopicSnapshot(topics=names)
    for name in names:
        lower = name.lower()
        if lower.startswith("am-"):
            snapshot.am_topics.append(name)
        elif lower.startswith("dashboard-"):
            snapshot.dashboard_topics.append(name)
        elif lower.endswith(".dlq"):
            snapshot.dlq_topics.append(name)
    return snapshot


async def refresh_topic_cache() -> KafkaTopicSnapshot | None:
    return await _get_cache().get_or_refresh(_refresh)


def snapshot() -> KafkaTopicSnapshot | None:
    return _get_cache().snapshot()


def exists(topic: str) -> bool:
    snap = snapshot()
    if not snap:
        return True
    return normalize_topic(topic) in snap.topics


def fuzzy_match(token: str, *, cutoff: float = 0.75) -> str | None:
    snap = snapshot()
    if not snap or not snap.topics:
        return None
    normalized = normalize_topic(token)
    if normalized in snap.topics:
        return normalized
    matches = difflib.get_close_matches(normalized, snap.topics, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def snippet(*, max_am: int = 25) -> str:
    snap = snapshot()
    if not snap or not snap.topics:
        return "Kafka topics: (cache offline — use list_topics or naming convention am-*, dashboard-*)"
    lines = [f"Kafka topics (live cache, {len(snap.topics)} total):"]
    am = snap.am_topics[:max_am]
    if am:
        extra = len(snap.am_topics) - len(am)
        suffix = f" (+{extra} more)" if extra > 0 else ""
        lines.append(f"  am-*: {', '.join(am)}{suffix}")
    if snap.dashboard_topics:
        lines.append(f"  dashboard-*: {', '.join(snap.dashboard_topics[:8])}")
    if snap.dlq_topics:
        lines.append(f"  DLQ: {', '.join(snap.dlq_topics[:6])}")
    lines.append("Use list_topics for full cluster catalog.")
    return "\n".join(lines)


def catalog_source() -> str:
    cache = _get_cache()
    if not cache.enabled:
        return "offline"
    return "live" if cache.is_fresh() else "stale"


def reset_cache_for_tests() -> None:
    global _cache
    if _cache:
        _cache.clear()
    _cache = None
