from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from qdrant_client import QdrantClient

from app.config import settings

logger = logging.getLogger(__name__)


class QdrantAdapter:
    def __init__(self) -> None:
        self._client: QdrantClient | None = None
        if settings.QDRANT_URL:
            try:
                parsed = urlparse(settings.QDRANT_URL)
                host = parsed.hostname or "localhost"
                port = parsed.port or (443 if parsed.scheme == "https" else 6333)
                https = parsed.scheme == "https"
                self._client = QdrantClient(
                    host=host,
                    port=port,
                    https=https,
                    api_key=settings.QDRANT_API_KEY or None,
                    check_compatibility=False,
                )
            except Exception as exc:
                logger.warning("Qdrant adapter unavailable: %s", exc)

    @property
    def available(self) -> bool:
        return self._client is not None

    async def execute(
        self, operation: str, params: dict[str, Any], *, read_only: bool, max_rows: int
    ) -> Any:
        if not self._client:
            raise RuntimeError("Qdrant not configured (set QDRANT_URL)")

        if operation == "list_collections":
            cols = self._client.get_collections().collections
            return {
                "collections": [
                    {"name": c.name, "points_count": getattr(c, "points_count", None)}
                    for c in cols
                ]
            }

        if operation == "collection_info":
            name = params.get("collection") or params.get("name")
            if not name:
                raise ValueError("collection name required")
            info = self._client.get_collection(name)
            return {
                "name": name,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "status": str(info.status),
            }

        if operation == "scroll":
            name = params.get("collection")
            if not name:
                raise ValueError("collection required")
            points, next_offset = self._client.scroll(
                collection_name=name,
                limit=min(max_rows, int(params.get("limit", max_rows))),
                with_payload=bool(params.get("with_payload", True)),
                with_vectors=False,
            )
            return {
                "collection": name,
                "points": [
                    {"id": str(p.id), "payload": p.payload} for p in points
                ],
                "next_offset": next_offset,
            }

        if operation == "search":
            name = params.get("collection")
            vector = params.get("vector")
            if not name or not vector:
                raise ValueError("collection and vector required")
            hits = self._client.search(
                collection_name=name,
                query_vector=vector,
                limit=min(max_rows, int(params.get("limit", 10))),
            )
            return {
                "collection": name,
                "hits": [
                    {"id": str(h.id), "score": h.score, "payload": h.payload}
                    for h in hits
                ],
            }

        raise ValueError(f"Unsupported Qdrant operation: {operation}")
