from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.intent_schema import BACKEND_OPERATIONS, BackendName, IntentDocument
from app.llm_client import get_llm_client
from app.config import settings
from app.observability.tracer import tracer
from app.observability.trace_labels import (
    generation_intent_name,
    parse_intent_input,
    parse_intent_output,
    parse_intent_span_name,
)
from app.observability.usage import LlmUsageRecord, UsageLedger
from app.resolve_params import extract_email, extract_uuid, infer_entity_from_text
from app.schema_catalog import get_schema_catalog
from app.state import DbAgentState

logger = logging.getLogger(__name__)

_INTENT_SYSTEM = """You parse natural-language infra database questions into JSON.
Return ONLY valid JSON (no markdown):
{
  "backend": "postgres|mongodb|redis|kafka|qdrant|influx|grafana|loki",
  "operation": "<operation from catalog>",
  "params": {},
  "read_only": true,
  "confidence": 0.0-1.0,
  "rationale": "short explanation"
}

Operation catalog:
- postgres: search_schema, run_sql, table_row_count
- mongodb: list_databases, list_collections, find, aggregate, collection_schema, count_documents
- redis: scan_keys, get, info, type
- kafka: list_topics, describe_topic, peek_messages, consumer_lag
- qdrant: list_collections, collection_info, scroll, search
- grafana: search_dashboards, get_dashboard, query_datasource
- influx: query_flux, query_influxql
- loki: query_logs, list_labels, list_label_values, query_patterns
"""


def _intent_system_prompt() -> str:
    catalog = get_schema_catalog()
    return f"{_INTENT_SYSTEM}\n\n{catalog.catalog_snippet()}"


def _mongo_default_database() -> str:
    return get_schema_catalog().default_database("mongodb") or "portfolio"


def _mongo_find_params(query: str) -> dict[str, Any]:
    db = _mongo_default_database()
    coll = "portfolios"
    filt: dict[str, Any] = {}
    entity = infer_entity_from_text(query)
    if entity:
        mapping = get_schema_catalog().entity(entity)
        if mapping and mapping.backend == "mongodb":
            if mapping.database:
                db = mapping.database
            if mapping.collection:
                coll = mapping.collection
    uuid = extract_uuid(query)
    if uuid:
        id_field = "_id"
        if entity:
            mapping = get_schema_catalog().entity(entity)
            if mapping:
                id_field = mapping.id_field
        filt[id_field] = uuid
    return {"database": db, "collection": coll, "filter": filt}


def _parse_llm_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data


KAFKA_TOPIC_PATTERN = re.compile(r"\b([a-z][a-z0-9_-]*(?:-[a-z0-9_-]+)+)\b", re.IGNORECASE)


def _extract_kafka_topic(query: str) -> str | None:
    """Extract a Kafka topic name from NL (e.g. am-stock-price-update)."""
    q = query.lower()
    for token in re.findall(r"[\w.-]+", query):
        if token.startswith("am-") and len(token) > 3:
            return token
    for pattern in (
        r"topic[s]?\s+([a-z][\w.-]+)",
        r"on\s+([a-z][\w.-]+)\s+topic",
        r"from\s+([a-z][\w.-]+)",
    ):
        match = re.search(pattern, q)
        if match:
            candidate = match.group(1)
            if candidate not in {"kafka", "topics", "topic", "cluster", "infra", "message", "messages"}:
                return candidate
    for match in KAFKA_TOPIC_PATTERN.finditer(query):
        candidate = match.group(1)
        if candidate.startswith("am-"):
            return candidate
    return None


def _kafka_rule_intent(query: str, backend_hint: BackendName | None) -> IntentDocument | None:
    q = query.lower()
    if not (backend_hint == "kafka" or "kafka" in q):
        return None

    topic = _extract_kafka_topic(query)
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
            "consume",
        )
    )
    wants_describe = topic and any(w in q for w in ("describe", "metadata", "partitions", "partition"))
    wants_lag = any(w in q for w in ("lag", "consumer group", "consumer_group"))

    if wants_messages:
        if not topic:
            return IntentDocument(
                backend="kafka",
                operation="list_topics",
                params={},
                confidence=0.55,
                rationale="Rule: kafka peek requested but topic name not found — listing topics",
            )
        limit = 1 if any(w in q for w in ("last", "latest", "most recent")) else 10
        return IntentDocument(
            backend="kafka",
            operation="peek_messages",
            params={"topic": topic, "limit": limit, "from_tail": True},
            confidence=0.85,
            rationale="Rule: kafka peek messages",
        )

    if wants_lag:
        params: dict[str, Any] = {}
        if topic:
            params["topic"] = topic
        group_match = re.search(r"(?:group|consumer group)\s+([\w.-]+)", q)
        if group_match:
            params["group"] = group_match.group(1)
        return IntentDocument(
            backend="kafka",
            operation="consumer_lag",
            params=params,
            confidence=0.75,
            rationale="Rule: kafka consumer lag",
        )

    if wants_describe and topic:
        return IntentDocument(
            backend="kafka",
            operation="describe_topic",
            params={"topic": topic},
            confidence=0.8,
            rationale="Rule: kafka describe topic",
        )

    if topic and not wants_messages:
        return IntentDocument(
            backend="kafka",
            operation="describe_topic",
            params={"topic": topic},
            confidence=0.7,
            rationale="Rule: kafka topic name detected",
        )

    return IntentDocument(
        backend="kafka",
        operation="list_topics",
        params={},
        confidence=0.75,
        rationale="Rule: kafka list topics",
    )


def _rule_based_intent(query: str, backend_hint: BackendName | None) -> IntentDocument | None:
    q = query.lower()

    if backend_hint == "qdrant" or "qdrant" in q or "collection" in q and "vector" in q:
        if "search" in q:
            coll = None
            for token in re.findall(r"[\w_-]+", query):
                if token not in {"search", "qdrant", "in", "for", "collection"}:
                    coll = token
                    break
            return IntentDocument(
                backend="qdrant",
                operation="search",
                params={"collection": coll or "ui_patterns", "query": query},
                confidence=0.7,
                rationale="Rule: qdrant search",
            )
        if "count" in q or "points" in q or "info" in q:
            match = re.search(r"([\w_-]+)", query)
            coll = match.group(1) if match and "collection" not in match.group(1).lower() else None
            for token in re.findall(r"[\w_-]+", query):
                if token not in {"how", "many", "points", "in", "qdrant", "collection", "info"}:
                    coll = token
                    break
            if coll:
                return IntentDocument(
                    backend="qdrant",
                    operation="collection_info",
                    params={"collection": coll},
                    confidence=0.75,
                    rationale="Rule: qdrant collection info",
                )
        return IntentDocument(
            backend="qdrant",
            operation="list_collections",
            params={},
            confidence=0.85,
            rationale="Rule: list qdrant collections",
        )

    if backend_hint == "loki" or "loki" in q or ("log" in q and "grafana" in q):
        return IntentDocument(
            backend="loki",
            operation="query_logs",
            params={"query": '{job=~".+"}', "limit": 50},
            confidence=0.7,
            rationale="Rule: loki log query (refine via /execute)",
        )

    if backend_hint == "redis" or "redis" in q:
        uuid = extract_uuid(query)
        if uuid and ("session" in q or "get" in q or "key" in q):
            return IntentDocument(
                backend="redis",
                operation="get",
                params={"entity": "session", "id": uuid},
                confidence=0.8,
                rationale="Rule: redis session key lookup",
            )
        pattern = "*"
        if "session" in q:
            pattern = "session:*"
        elif "portfolio" in q:
            pattern = "portfolio:*"
        elif re.search(r"[\*\w:-]+", query):
            pattern = re.search(r"([\*\w:-]+)", query).group(1)  # type: ignore[union-attr]
        return IntentDocument(
            backend="redis",
            operation="scan_keys",
            params={"pattern": pattern},
            confidence=0.8,
            rationale="Rule: redis key scan",
        )

    if backend_hint == "mongodb" or "mongo" in q:
        default_db = _mongo_default_database()
        email = extract_email(query)
        if email and re.search(r"\busers?\b", q):
            return IntentDocument(
                backend="mongodb",
                operation="find",
                params={
                    "entity": "user",
                    "lookup_field": "email",
                    "lookup_value": email,
                },
                confidence=0.85,
                rationale="Rule: mongo user lookup by email",
            )
        if any(w in q for w in ("how many", "count", "number of", "no of", "no. of")):
            db = default_db
            coll = "portfolios"
            for token in re.findall(r"[\w_-]+", query):
                if token.lower() == "portfolios":
                    coll = "portfolios"
                elif token.lower() == "users":
                    coll = "users"
            filt: dict[str, Any] = {}
            uuid = extract_uuid(query)
            if uuid:
                mapping = get_schema_catalog().entity(infer_entity_from_text(query) or "portfolio")
                id_field = mapping.id_field if mapping else "_id"
                filt[id_field] = uuid
            return IntentDocument(
                backend="mongodb",
                operation="count_documents",
                params={"database": db, "collection": coll, "filter": filt},
                confidence=0.85,
                rationale="Rule: mongo document count",
            )
        if "list collection" in q or "collections" in q:
            db = default_db if "portfolio" in q else "admin"
            return IntentDocument(
                backend="mongodb",
                operation="list_collections",
                params={"database": db},
                confidence=0.8,
                rationale="Rule: list mongo collections",
            )
        if "find" in q or "search" in q or extract_uuid(query):
            return IntentDocument(
                backend="mongodb",
                operation="find",
                params=_mongo_find_params(query),
                confidence=0.75 if extract_uuid(query) else 0.7,
                rationale="Rule: mongo find",
            )
        return IntentDocument(
            backend="mongodb",
            operation="list_databases",
            params={},
            confidence=0.8,
            rationale="Rule: list mongo databases",
        )

    if backend_hint == "postgres" or "postgres" in q or "sql" in q:
        uuid = extract_uuid(query)
        email = extract_email(query)
        if email and re.search(r"\busers?\b", q):
            return IntentDocument(
                backend="postgres",
                operation="run_sql",
                params={
                    "entity": "user_account",
                    "lookup_field": "email",
                    "lookup_value": email,
                },
                confidence=0.85,
                rationale="Rule: postgres user lookup by email",
            )
        if email and re.search(r"\busers?\b", q) is None and "portfolio" in q:
            return IntentDocument(
                backend="postgres",
                operation="run_sql",
                params={
                    "entity": "portfolio_pg",
                    "lookup_field": "email",
                    "lookup_value": email,
                },
                confidence=0.75,
                rationale="Rule: postgres lookup by email",
            )
        if uuid and ("portfolio" in q or "user" in q or "find" in q or "get" in q):
            entity = (
                "portfolio_pg"
                if "portfolio" in q
                else "user_account"
                if "user" in q
                else "portfolio_pg"
            )
            return IntentDocument(
                backend="postgres",
                operation="run_sql",
                params={"entity": entity, "id": uuid},
                confidence=0.8,
                rationale="Rule: postgres row lookup by entity",
            )
        if any(w in q for w in ("how many", "count", "number of", "row count")):
            entity = (
                "portfolio_pg"
                if "portfolio" in q
                else "user_account"
                if "user" in q
                else None
            )
            params: dict[str, Any] = {}
            if entity:
                params["entity"] = entity
            else:
                params["pattern"] = "portfolio"
            return IntentDocument(
                backend="postgres",
                operation="table_row_count" if entity else "search_schema",
                params=params,
                confidence=0.75,
                rationale="Rule: postgres count or schema search",
            )
        return IntentDocument(
            backend="postgres",
            operation="search_schema",
            params={"pattern": "user_accounts" if "user" in q else "portfolio" if "portfolio" in q else "%"},
            confidence=0.7,
            rationale="Rule: postgres schema search",
        )

    kafka_intent = _kafka_rule_intent(query, backend_hint)
    if kafka_intent is not None:
        return kafka_intent

    if backend_hint:
        ops = BACKEND_OPERATIONS.get(backend_hint, [])
        if ops:
            return IntentDocument(
                backend=backend_hint,
                operation=ops[0],
                params={},
                confidence=0.6,
                rationale=f"Rule: default op for hinted backend {backend_hint}",
            )
    return None


async def parse_intent_node(state: DbAgentState) -> DbAgentState:
    request = state["request"]
    request_id = state["request_id"]
    query = request.query.strip()
    backend_hint = request.backend
    ledger = state.get("usage_ledger") or UsageLedger()

    intent: IntentDocument | None = None
    llm = get_llm_client()
    parse_source: str = "rules"
    llm_result = None
    gateway_trace_id = state.get("gateway_trace_id")

    if backend_hint:
        intent = _rule_based_intent(query, backend_hint)

    if intent is None and settings.LLM_INTENT_ENABLED and llm.available:
        try:
            llm_result = await llm.chat_with_usage(
                system=_intent_system_prompt(),
                user=f"Query: {query}\nBackend hint: {backend_hint or 'none'}",
                request_id=request_id,
                generation_name="db-agent-intent",
            )
            data = _parse_llm_json(llm_result.content)
            intent = IntentDocument.model_validate(data)
            parse_source = "llm"
            if llm_result.gateway_trace_id:
                gateway_trace_id = llm_result.gateway_trace_id
        except Exception as exc:
            logger.warning("LLM intent parse failed, using rules: %s", exc)

    if intent is None:
        intent = _rule_based_intent(query, backend_hint)

    if intent is None:
        await tracer.span(
            request_id,
            "parse intent · failed",
            input=parse_intent_input(query=query, backend_hint=backend_hint),
            output={"status": "error", "message": "Could not parse intent from query"},
            metadata={"step": "parse_intent", "description": "Intent parsing failed"},
            level="ERROR",
        )
        return {**state, "error": "Could not parse intent from query", "error_status": 400}

    intent = intent.model_copy(update={"read_only": request.read_only})

    if backend_hint and intent.backend != backend_hint:
        intent = intent.model_copy(update={"backend": backend_hint, "confidence": min(intent.confidence, 0.9)})

    span_metadata: dict[str, object] = {"rationale": intent.rationale}
    if llm_result is not None:
        usage_record = LlmUsageRecord(
            name=generation_intent_name(),
            model=llm_result.model,
            prompt_tokens=llm_result.usage.get("prompt_tokens", 0),
            completion_tokens=llm_result.usage.get("completion_tokens", 0),
            total_tokens=llm_result.usage.get("total_tokens", 0),
            cost_usd=llm_result.cost_usd,
            latency_ms=llm_result.latency_ms,
        )
        ledger.add_llm(usage_record)
        span_metadata.update(
            {
                "tokens": usage_record.total_tokens,
                "prompt_tokens": usage_record.prompt_tokens,
                "completion_tokens": usage_record.completion_tokens,
                "cost_usd": usage_record.cost_usd,
            }
        )

    span_id = await tracer.span(
        request_id,
        parse_intent_span_name(
            parse_source=parse_source,
            backend=intent.backend,
            operation=intent.operation,
        ),
        input=parse_intent_input(query=query, backend_hint=backend_hint),
        output=parse_intent_output(intent=intent, parse_source=parse_source),
        metadata={
            "step": "parse_intent",
            "parse_source": parse_source,
            "source_name": parse_source,
            **span_metadata,
        },
    )

    if llm_result is not None and llm.routing == "direct":
        await tracer.generation(
            request_id,
            generation_intent_name(),
            model=llm_result.model,
            input=parse_intent_input(query=query, backend_hint=backend_hint),
            output=llm_result.content,
            usage=llm_result.usage,
            cost_usd=llm_result.cost_usd,
            latency_ms=llm_result.latency_ms,
            parent_observation_id=span_id,
            metadata={"step": "parse_intent", "source_name": "litellm/direct"},
        )
    elif llm_result is not None and llm_result.gateway_trace_id:
        span_metadata["gateway_trace_id"] = llm_result.gateway_trace_id

    return {
        **state,
        "intent": intent,
        "usage_ledger": ledger,
        "parse_source": parse_source,
        "gateway_trace_id": gateway_trace_id,
    }
