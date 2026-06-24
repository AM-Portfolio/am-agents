import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import settings
from app.memory.embedder import UI_PATTERN_DIM

logger = logging.getLogger(__name__)


class QdrantMemory:
    def __init__(self):
        self.host = settings.QDRANT_HOST
        self.port = settings.QDRANT_PORT
        self.api_key = settings.QDRANT_API_KEY
        self.client: QdrantClient | None = None

        try:
            scheme = "https" if settings.QDRANT_HTTPS else "http"
            logger.info(
                "Connecting to Qdrant at %s://%s:%s...",
                scheme,
                self.host,
                self.port,
            )
            self.client = QdrantClient(
                host=self.host,
                port=self.port,
                https=settings.QDRANT_HTTPS,
                api_key=self.api_key,
                check_compatibility=False,
            )
            self._ensure_collections()
        except Exception as e:
            logger.error("Failed to connect to Qdrant: %s. Qdrant operations will be bypassed.", e)
            self.client = None

    @property
    def available(self) -> bool:
        return self.client is not None

    def _ensure_collections(self):
        collections_to_create = {
            "ui_patterns": UI_PATTERN_DIM,
            "test_cases": 1536,
            "selectors": 1536,
            "bug_memory": UI_PATTERN_DIM,
        }

        existing = [c.name for c in self.client.get_collections().collections]
        for name, dim in collections_to_create.items():
            if name not in existing:
                logger.info("Creating Qdrant collection: %s (dim=%d)", name, dim)
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )

    def _baseline_filter(self, profile: str, route: str, step_label: str, *, active_only: bool = True) -> Filter:
        must = [
            FieldCondition(key="profile", match=MatchValue(value=profile)),
            FieldCondition(key="route", match=MatchValue(value=route)),
            FieldCondition(key="step_label", match=MatchValue(value=step_label)),
        ]
        if active_only:
            must.append(FieldCondition(key="status", match=MatchValue(value="active")))
        return Filter(must=must)

    def get_active_baseline(
        self, profile: str, route: str, step_label: str
    ) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        try:
            points, _ = self.client.scroll(
                collection_name="ui_patterns",
                scroll_filter=self._baseline_filter(profile, route, step_label),
                limit=1,
                with_payload=True,
                with_vectors=True,
            )
            if not points:
                return None
            point = points[0]
            return {
                "id": str(point.id),
                "payload": point.payload or {},
                "vector": list(point.vector) if point.vector else [],
            }
        except Exception as e:
            logger.error("Error fetching active baseline: %s", e)
            return None

    def search_ui_pattern(
        self,
        *,
        profile: str,
        route: str,
        step_label: str,
        vector: List[float],
        limit: int = 1,
    ) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        try:
            hits = self.client.search(
                collection_name="ui_patterns",
                query_vector=vector,
                query_filter=self._baseline_filter(profile, route, step_label),
                limit=limit,
            )
            return [
                {
                    "id": str(hit.id),
                    "score": float(hit.score),
                    "payload": hit.payload or {},
                }
                for hit in hits
            ]
        except Exception as e:
            logger.error("Error searching ui_patterns: %s", e)
            return []

    def search_bug_memory(self, vector: List[float], limit: int = 1) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        try:
            hits = self.client.search(
                collection_name="bug_memory",
                query_vector=vector,
                limit=limit,
            )
            return [
                {"id": str(hit.id), "score": float(hit.score), "payload": hit.payload or {}}
                for hit in hits
            ]
        except Exception as e:
            logger.error("Error searching bug_memory: %s", e)
            return []

    def _supersede_active_baselines(self, profile: str, route: str, step_label: str) -> None:
        if not self.client:
            return
        try:
            points, _ = self.client.scroll(
                collection_name="ui_patterns",
                scroll_filter=self._baseline_filter(profile, route, step_label),
                limit=100,
                with_payload=True,
            )
            for point in points:
                payload = dict(point.payload or {})
                payload["status"] = "superseded"
                payload["superseded_at"] = datetime.now(timezone.utc).isoformat()
                self.client.set_payload(
                    collection_name="ui_patterns",
                    payload=payload,
                    points=[point.id],
                )
        except Exception as e:
            logger.error("Error superseding baselines: %s", e)

    def _next_design_version(self, profile: str, route: str, step_label: str) -> int:
        if not self.client:
            return 1
        try:
            points, _ = self.client.scroll(
                collection_name="ui_patterns",
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="profile", match=MatchValue(value=profile)),
                        FieldCondition(key="route", match=MatchValue(value=route)),
                        FieldCondition(key="step_label", match=MatchValue(value=step_label)),
                    ]
                ),
                limit=200,
                with_payload=True,
            )
            versions = [int((p.payload or {}).get("design_version", 0)) for p in points]
            return max(versions, default=0) + 1
        except Exception as e:
            logger.error("Error reading design versions: %s", e)
            return 1

    def upsert_ui_pattern(
        self,
        *,
        profile: str,
        route: str,
        step_label: str,
        vector: List[float],
        screenshot_ref: str,
        commit_sha: Optional[str] = None,
        test_id: Optional[str] = None,
        supersede_existing: bool = True,
    ) -> Dict[str, Any]:
        if not self.client:
            return {}
        if supersede_existing:
            self._supersede_active_baselines(profile, route, step_label)
        design_version = self._next_design_version(profile, route, step_label)
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "profile": profile,
            "route": route,
            "step_label": step_label,
            "design_version": design_version,
            "commit_sha": commit_sha or "",
            "test_id": test_id or "",
            "screenshot_ref": screenshot_ref,
            "status": "active",
            "approved_at": now,
        }
        point_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"ui_pattern:{profile}:{route}:{step_label}:v{design_version}",
            )
        )
        try:
            self.client.upsert(
                collection_name="ui_patterns",
                points=[PointStruct(id=point_id, vector=vector, payload=payload)],
            )
            logger.info(
                "Upserted ui_pattern %s/%s/%s v%s",
                profile,
                route,
                step_label,
                design_version,
            )
            return {"point_id": point_id, "design_version": design_version, **payload}
        except Exception as e:
            logger.error("Error upserting ui_pattern: %s", e)
            return {}

    async def search_selectors(self, logical_name: str, limit: int = 1) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        try:
            return []
        except Exception as e:
            logger.error("Error querying selectors from Qdrant: %s", e)
            return []

    async def upsert_selector(
        self, logical_name: str, selector: str, coordinates: Optional[Dict[str, int]] = None
    ):
        if not self.client:
            return
        try:
            logger.info("Upserting selector to Qdrant: %s -> %s", logical_name, selector)
        except Exception as e:
            logger.error("Error upserting selector to Qdrant: %s", e)


qdrant_memory = QdrantMemory()
