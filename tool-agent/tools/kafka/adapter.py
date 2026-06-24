from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _kafka_conf(*, group_id: str | None = None) -> dict[str, Any]:
    if not settings.KAFKA_BOOTSTRAP_SERVERS:
        raise RuntimeError("Kafka not configured (set KAFKA_BOOTSTRAP_SERVERS)")

    conf: dict[str, Any] = {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
    }
    if group_id:
        conf["group.id"] = group_id
    if settings.KAFKA_USERNAME and settings.KAFKA_PASSWORD:
        conf.update(
            {
                "security.protocol": settings.KAFKA_SECURITY_PROTOCOL,
                "sasl.mechanism": settings.KAFKA_SASL_MECHANISM,
                "sasl.username": settings.KAFKA_USERNAME,
                "sasl.password": settings.KAFKA_PASSWORD,
            }
        )
    return conf


def _list_topics_sync(*, max_rows: int) -> dict[str, Any]:
    from confluent_kafka.admin import AdminClient

    admin = AdminClient(_kafka_conf())
    metadata = admin.list_topics(timeout=15)
    topics = []
    for name, topic_meta in sorted(metadata.topics.items()):
        if name.startswith("_"):
            continue
        topics.append(
            {
                "name": name,
                "partitions": len(topic_meta.partitions),
            }
        )
    return {"topics": topics[:max_rows], "count": len(topics)}


def _describe_topic_sync(topic: str) -> dict[str, Any]:
    from confluent_kafka.admin import AdminClient

    admin = AdminClient(_kafka_conf())
    metadata = admin.list_topics(topic=topic, timeout=15)
    topic_meta = metadata.topics.get(topic)
    if topic_meta is None or topic_meta.error is not None:
        err = topic_meta.error if topic_meta else "topic not found"
        raise ValueError(f"Topic '{topic}' not found: {err}")

    partitions = []
    for pid, part in sorted(topic_meta.partitions.items()):
        partitions.append(
            {
                "partition": pid,
                "leader": part.leader,
                "replicas": list(part.replicas),
                "isrs": list(part.isrs),
            }
        )
    return {"topic": topic, "partitions": partitions, "partition_count": len(partitions)}


def _message_payload(msg: Any) -> dict[str, Any]:
    value = msg.value()
    return {
        "partition": msg.partition(),
        "offset": msg.offset(),
        "key": msg.key().decode("utf-8", errors="replace") if msg.key() else None,
        "value": value.decode("utf-8", errors="replace") if value else None,
        "timestamp": msg.timestamp()[1] if msg.timestamp()[0] else None,
    }


def _is_kafka_broker_reachability_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "host resolution failure",
            "_resolve",
            "failed to resolve",
            "broker transport failure",
            "_transport",
        )
    )


def _kafka_ui_configured() -> bool:
    return bool(settings.KAFKA_UI_URL and settings.KAFKA_UI_CLUSTER)


def _parse_kafka_ui_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp() * 1000)
    except ValueError:
        return None


def _peek_messages_via_ui_sync(topic: str, *, limit: int, from_tail: bool) -> dict[str, Any]:
    if not _kafka_ui_configured():
        raise RuntimeError(
            "Kafka broker is not reachable from this host and KAFKA_UI_URL is not configured"
        )

    base = settings.KAFKA_UI_URL.rstrip("/")
    cluster = settings.KAFKA_UI_CLUSTER
    url = f"{base}/api/clusters/{cluster}/topics/{topic}/messages"
    params = {
        "limit": limit,
        "seekType": "LATEST" if from_tail else "BEGINNING",
        "seekDirection": "BACKWARD" if from_tail else "FORWARD",
    }

    messages: list[dict[str, Any]] = []
    with httpx.Client(timeout=settings.TOOL_AGENT_TIMEOUT_SECONDS, follow_redirects=True) as client:
        with client.stream("GET", url, params=params) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = json.loads(line[5:])
                if payload.get("type") != "MESSAGE":
                    continue
                msg = payload["message"]
                messages.append(
                    {
                        "partition": msg.get("partition"),
                        "offset": msg.get("offset"),
                        "key": msg.get("key"),
                        "value": msg.get("content"),
                        "timestamp": _parse_kafka_ui_timestamp(msg.get("timestamp")),
                        "headers": msg.get("headers"),
                    }
                )
                if len(messages) >= limit:
                    break

    if from_tail and limit == 1 and len(messages) > 1:
        messages = [max(messages, key=lambda m: (m.get("timestamp") or 0, m.get("offset") or 0))]

    return {
        "topic": topic,
        "messages": messages[:limit],
        "count": len(messages[:limit]),
        "peek_source": "kafka-ui",
    }


def _peek_messages_sync(topic: str, *, limit: int, from_tail: bool = False) -> dict[str, Any]:
    from confluent_kafka import Consumer, KafkaException, TopicPartition

    group_id = f"tool-agent-peek-{uuid.uuid4().hex[:12]}"
    conf = _kafka_conf(group_id=group_id)
    conf.update(
        {
            "auto.offset.reset": "latest" if from_tail else "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer = Consumer(conf)
    messages: list[dict[str, Any]] = []
    try:
        metadata = consumer.list_topics(topic, timeout=15)
        topic_meta = metadata.topics.get(topic)
        if topic_meta is None or topic_meta.error is not None:
            raise ValueError(f"Topic '{topic}' not found")

        partition_ids = sorted(topic_meta.partitions.keys())
        if not partition_ids:
            return {"topic": topic, "messages": [], "count": 0}

        if from_tail:
            assigned: list[TopicPartition] = []
            for pid in partition_ids:
                tp = TopicPartition(topic, pid)
                _low, high = consumer.get_watermark_offsets(tp, timeout=15)
                if high > 0:
                    tp.offset = high - 1
                    assigned.append(tp)
            if not assigned:
                return {"topic": topic, "messages": [], "count": 0}
            consumer.assign(assigned)
            empty_polls = 0
            while len(messages) < limit and empty_polls < 10:
                msg = consumer.poll(1.0)
                if msg is None:
                    empty_polls += 1
                    continue
                if msg.error():
                    raise KafkaException(msg.error())
                empty_polls = 0
                messages.append(_message_payload(msg))
            if limit == 1 and len(messages) > 1:
                messages = [max(messages, key=lambda m: (m.get("timestamp") or 0, m.get("offset") or 0))]
            return {"topic": topic, "messages": messages[:limit], "count": len(messages[:limit])}

        consumer.assign([TopicPartition(topic, partition_ids[0])])
        empty_polls = 0
        while len(messages) < limit and empty_polls < 5:
            msg = consumer.poll(1.0)
            if msg is None:
                empty_polls += 1
                continue
            if msg.error():
                raise KafkaException(msg.error())
            empty_polls = 0
            messages.append(_message_payload(msg))
        return {"topic": topic, "messages": messages, "count": len(messages)}
    finally:
        consumer.close()


def _peek_messages(topic: str, *, limit: int, from_tail: bool) -> dict[str, Any]:
    mode = settings.KAFKA_PEEK_MODE
    if mode == "kafka_ui":
        return _peek_messages_via_ui_sync(topic, limit=limit, from_tail=from_tail)

    try:
        result = _peek_messages_sync(topic, limit=limit, from_tail=from_tail)
        result["peek_source"] = "native"
        return result
    except Exception as exc:
        if mode == "native" or not _kafka_ui_configured() or not _is_kafka_broker_reachability_error(exc):
            raise
        logger.warning(
            "Native Kafka peek failed (%s); falling back to Kafka UI at %s",
            exc,
            settings.KAFKA_UI_URL,
        )
        return _peek_messages_via_ui_sync(topic, limit=limit, from_tail=from_tail)


def _consumer_lag_sync(
    *,
    topic: str | None,
    group: str | None,
    max_rows: int,
) -> dict[str, Any]:
    from confluent_kafka.admin import AdminClient

    admin = AdminClient(_kafka_conf())
    if not group:
        result = admin.list_consumer_groups(request_timeout=15)
        groups = result.result()
        names = sorted({g.group_id for g in groups.valid})[:max_rows]
        return {"consumer_groups": names, "count": len(names)}

    described = admin.describe_consumer_groups([group], request_timeout=15)
    group_desc = described[group].result()
    if group_desc.error is not None:
        raise ValueError(f"Consumer group '{group}' not found: {group_desc.error}")

    members = []
    for member in group_desc.members:
        assignments = []
        if member.assignment:
            assignments = [
                {"topic": tp.topic, "partition": tp.partition}
                for tp in member.assignment.topic_partitions
            ]
        members.append(
            {
                "member_id": member.member_id,
                "client_id": member.client_id,
                "assignments": assignments,
            }
        )

    payload: dict[str, Any] = {
        "group": group,
        "state": str(group_desc.state),
        "members": members[:max_rows],
        "member_count": len(members),
    }
    if topic:
        payload["topic_filter"] = topic
    return payload


class KafkaAdapter:
    @property
    def available(self) -> bool:
        return bool(settings.KAFKA_BOOTSTRAP_SERVERS)

    async def execute(
        self, operation: str, params: dict[str, Any], *, read_only: bool, max_rows: int
    ) -> Any:
        if operation == "list_topics":
            return await asyncio.to_thread(_list_topics_sync, max_rows=max_rows)

        if operation == "describe_topic":
            topic = params.get("topic")
            if not topic:
                raise ValueError("topic required")
            return await asyncio.to_thread(_describe_topic_sync, str(topic))

        if operation == "peek_messages":
            topic = params.get("topic")
            if not topic:
                raise ValueError("topic required")
            limit = min(int(params.get("limit", max_rows)), max_rows)
            from_tail = bool(params.get("from_tail", False))
            return await asyncio.to_thread(
                _peek_messages, str(topic), limit=limit, from_tail=from_tail
            )

        if operation == "consumer_lag":
            return await asyncio.to_thread(
                _consumer_lag_sync,
                topic=params.get("topic"),
                group=params.get("group") or params.get("consumer_group"),
                max_rows=max_rows,
            )

        raise ValueError(f"Unsupported Kafka operation: {operation}")
