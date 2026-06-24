from __future__ import annotations

import re
from typing import Any

from app.models.intent import IntentDocument
from app.schema.loader import get_schema_catalog

_NS_RE = re.compile(r"\b(?:in|for)\s+([a-z0-9][a-z0-9-]*)\s+(?:namespace|ns)\b", re.I)
_NS_BEFORE_TIME_RE = re.compile(r"\bin\s+([a-z0-9][a-z0-9-]*)\s+last\b", re.I)
_POD_RE = re.compile(r"\b(?:pod|deployment|app)\s+([a-z0-9][a-z0-9-]*)\b", re.I)
_FOR_SERVICE_RE = re.compile(r"\b(?:logs?|loki)\s+for\s+([a-z0-9][a-z0-9-]*)\b", re.I)
_TIME_RE = re.compile(r"\blast\s+(\d+)\s*(m|min|mins|minutes|h|hr|hours|d|days)\b", re.I)
_ERROR_LOG_RE = re.compile(r"\berror\s*logs?\b|\berror\s+pattern\b|\berrors?\s+in\b|\bfind\s+errors?\b", re.I)


def _default_time_range() -> tuple[str, str]:
    catalog = get_schema_catalog()
    start = catalog.default_for("grafana", "start") or "now-1h"
    end = catalog.default_for("grafana", "end") or "now"
    return start, end


def _time_range_from_query(query: str) -> tuple[str, str]:
    match = _TIME_RE.search(query)
    if not match:
        return _default_time_range()
    amount, unit = match.group(1), match.group(2).lower()
    if unit.startswith("m"):
        return f"now-{amount}m", "now"
    if unit.startswith("h"):
        return f"now-{amount}h", "now"
    if unit.startswith("d"):
        return f"now-{amount}d", "now"
    return _default_time_range()


def _namespace_from_query(query: str) -> str | None:
    ns_match = _NS_RE.search(query) or _NS_BEFORE_TIME_RE.search(query)
    return ns_match.group(1) if ns_match else None


def _label_selector_from_query(query: str) -> str | None:
    if "{" in query and "}" in query:
        start = query.find("{")
        end = query.rfind("}") + 1
        return query[start:end]
    namespace = _namespace_from_query(query)
    pod_match = _POD_RE.search(query) or _FOR_SERVICE_RE.search(query)
    if namespace and pod_match:
        return f'{{namespace="{namespace}", pod=~"{pod_match.group(1)}.*"}}'
    if namespace:
        return f'{{namespace="{namespace}"}}'
    if pod_match:
        return f'{{pod=~"{pod_match.group(1)}.*"}}'
    return None


def _logql_from_query(query: str) -> str | None:
    return _label_selector_from_query(query)


def _error_logql_from_query(query: str) -> str:
    selector = _label_selector_from_query(query) or "{}"
    return f'{selector} |~ "(?i)(error|exception|failed)"'


def parse_rules(
    query: str, *, tool_name: str, backend_hint: str | None = None
) -> IntentDocument | None:
    q = query.lower()
    if backend_hint and backend_hint != tool_name:
        return None
    if not any(k in q for k in ("grafana", "loki", "log", "logs", "dashboard", "prometheus", "promql", "metric")):
        if backend_hint != tool_name:
            return None

    start, end = _time_range_from_query(query)

    if "dashboard" in q and ("search" in q or "find" in q or "list" in q):
        term = ""
        if " for " in q:
            term = query.split(" for ", 1)[-1].strip().strip('"').split()[0]
        else:
            for token in re.findall(r"[\w-]+", query):
                low = token.lower()
                if low not in (
                    "search", "find", "list", "grafana", "dashboard", "dashboards", "for",
                ):
                    term = token
                    break
        return IntentDocument(
            backend="grafana",
            operation="search_dashboards",
            params={"query": term or "dashboard"},
            confidence=0.8,
            rationale="Rule: search grafana dashboards",
        )

    if "datasource" in q or "data source" in q:
        return IntentDocument(
            backend="grafana",
            operation="list_datasources",
            params={},
            confidence=0.85,
            rationale="Rule: list grafana datasources",
        )

    if _ERROR_LOG_RE.search(q):
        return IntentDocument(
            backend="grafana",
            operation="query_logs",
            params={"query": _error_logql_from_query(query), "start": start, "end": end},
            confidence=0.85,
            rationale="Rule: error logs via LogQL (Sift not required)",
        )

    if "label" in q and "value" in q:
        return IntentDocument(
            backend="grafana",
            operation="list_label_values",
            params={},
            confidence=0.75,
            rationale="Rule: list loki label values",
        )

    if "label" in q:
        return IntentDocument(
            backend="grafana",
            operation="list_labels",
            params={},
            confidence=0.75,
            rationale="Rule: list loki labels",
        )

    if "promql" in q or "prometheus" in q or ("metric" in q and "log" not in q):
        expr = "up"
        if "{" in query:
            expr = query[query.find("{") : query.rfind("}") + 1]
        return IntentDocument(
            backend="grafana",
            operation="query_metrics",
            params={"expr": expr, "start": start, "end": end},
            confidence=0.75,
            rationale="Rule: prometheus query",
        )

    logql = _logql_from_query(query)
    if logql or any(w in q for w in ("log", "logs", "loki")):
        params: dict[str, Any] = {"start": start, "end": end}
        if logql:
            params["query"] = logql
        return IntentDocument(
            backend="grafana",
            operation="query_logs",
            params=params,
            confidence=0.85 if logql else 0.7,
            rationale="Rule: loki log query",
        )

    return None
