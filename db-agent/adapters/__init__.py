from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.kafka import GrafanaAdapter, InfluxAdapter, KafkaAdapter, LokiAdapter
from adapters.mongo import MongoAdapter
from adapters.postgres import PostgresAdapter
from adapters.qdrant import QdrantAdapter
from adapters.redis import RedisAdapter

if TYPE_CHECKING:
    from adapters.base import BaseAdapter

_adapters: dict[str, BaseAdapter] | None = None


def get_adapters() -> dict[str, BaseAdapter]:
    global _adapters
    if _adapters is None:
        _adapters = {
            "qdrant": QdrantAdapter(),
            "redis": RedisAdapter(),
            "postgres": PostgresAdapter(),
            "mongodb": MongoAdapter(),
            "kafka": KafkaAdapter(),
            "grafana": GrafanaAdapter(),
            "influx": InfluxAdapter(),
            "loki": LokiAdapter(),
        }
    return _adapters


async def run_adapter(
    backend: str,
    method: str,
    params: dict,
    *,
    read_only: bool,
    max_rows: int,
) -> object:
    adapters = get_adapters()
    adapter = adapters.get(backend)
    if not adapter or not adapter.available:
        raise RuntimeError(f"No available adapter for backend '{backend}'")
    return await adapter.execute(method, params, read_only=read_only, max_rows=max_rows)
