from __future__ import annotations

import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _normalize_filter(query: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(query)
    for key, value in list(normalized.items()):
        if isinstance(value, str) and UUID_PATTERN.match(value):
            try:
                from uuid import UUID

                normalized[key] = str(UUID(value))
            except ValueError:
                pass
    return normalized


def _uuid_filter_candidates(query: dict[str, Any]) -> list[dict[str, Any]]:
    """Build fallback filters when _id UUID lookup may use alternate fields."""
    candidates = [_normalize_filter(query)]
    for key, value in query.items():
        if not isinstance(value, str) or not UUID_PATTERN.match(value):
            continue
        if key == "_id":
            candidates.append({"portfolio_id": value})
        elif key != "portfolio_id":
            candidates.append({key: value})
    seen: list[str] = []
    unique: list[dict[str, Any]] = []
    for candidate in candidates:
        key = str(sorted(candidate.items()))
        if key not in seen:
            seen.append(key)
            unique.append(candidate)
    return unique


class MongoAdapter:
    @property
    def available(self) -> bool:
        return bool(settings.MONGODB_URI)

    async def execute(
        self, operation: str, params: dict[str, Any], *, read_only: bool, max_rows: int
    ) -> Any:
        if not settings.MONGODB_URI:
            raise RuntimeError("MongoDB not configured (set MONGODB_URI)")

        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(settings.MONGODB_URI)
        try:
            if operation == "list_databases":
                names = await client.list_database_names()
                return {"databases": names[:max_rows]}

            if operation == "list_collections":
                db_name = params.get("database")
                if not db_name:
                    raise ValueError("database required")
                cols = await client[db_name].list_collection_names()
                return {"database": db_name, "collections": cols[:max_rows]}

            if operation == "find":
                db_name = params.get("database")
                coll = params.get("collection")
                if not db_name or not coll:
                    raise ValueError("database and collection required")
                query = params.get("filter") or {}
                collection = client[db_name][coll]
                docs: list[dict[str, Any]] = []
                used_filter: dict[str, Any] = query
                for candidate in _uuid_filter_candidates(query):
                    cursor = collection.find(candidate).limit(max_rows)
                    docs = await cursor.to_list(length=max_rows)
                    if docs:
                        used_filter = candidate
                        break
                for doc in docs:
                    doc["_id"] = str(doc.get("_id"))
                return {"documents": docs, "count": len(docs), "filter": used_filter}

            if operation == "count_documents":
                db_name = params.get("database")
                coll = params.get("collection")
                if not db_name or not coll:
                    raise ValueError("database and collection required")
                query = params.get("filter") or {}
                collection = client[db_name][coll]
                total = 0
                used_filter: dict[str, Any] = query
                for candidate in _uuid_filter_candidates(query):
                    total = await collection.count_documents(candidate)
                    if total:
                        used_filter = candidate
                        break
                return {
                    "database": db_name,
                    "collection": coll,
                    "count": total,
                    "filter": used_filter,
                }

            raise ValueError(f"Unsupported MongoDB operation: {operation}")
        finally:
            client.close()
