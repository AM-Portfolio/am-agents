"""Document store adapters — memory (dev/test) + optional MinIO."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from am_support_agent.adapters.storage import DocStoreNamespace
from am_support_agent.contracts.capabilities import DocumentRef


class MemoryDocumentStore:
    name = "memory-documents"

    def __init__(self, *, namespace: DocStoreNamespace | None = None) -> None:
        self._ns = namespace or DocStoreNamespace()
        self._objects: dict[str, tuple[bytes, str]] = {}

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "wired": True,
            "bucket": self._ns.bucket() or "memory",
            "prefix": self._ns.prefix(),
            "objects": len(self._objects),
        }

    async def put(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> DocumentRef:
        key = self._ns.object_key(object_key)
        self._objects[key] = (content, content_type)
        return DocumentRef(
            bucket=self._ns.bucket() or "memory",
            object_key=key,
            checksum=hashlib.sha256(content).hexdigest(),
            content_type=content_type,
            size_bytes=len(content),
        )

    async def get(self, *, object_key: str) -> bytes:
        key = self._ns.object_key(object_key) if not object_key.startswith(self._ns.prefix()) else object_key
        if key not in self._objects:
            raise KeyError(f"document not found: {key}")
        return self._objects[key][0]

    async def exists(self, *, object_key: str) -> bool:
        key = self._ns.object_key(object_key) if not object_key.startswith(self._ns.prefix()) else object_key
        return key in self._objects


class MinioDocumentStore:
    name = "minio-documents"

    def __init__(self, *, namespace: DocStoreNamespace | None = None) -> None:
        self._ns = namespace or DocStoreNamespace()
        self._client = None
        self._error: str | None = None
        endpoint = (os.environ.get("MINIO_ENDPOINT") or "").strip()
        access_key = (os.environ.get("MINIO_ACCESS_KEY") or "").strip()
        secret_key = (os.environ.get("MINIO_SECRET_KEY") or "").strip()
        if not (endpoint and access_key and secret_key):
            self._error = "MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY required"
            return
        try:
            from minio import Minio
            from urllib.parse import urlparse

            parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
            host = parsed.hostname or endpoint
            port = parsed.port
            secure = parsed.scheme == "https"
            endpoint_host = f"{host}:{port}" if port else host
            self._client = Minio(endpoint_host, access_key=access_key, secret_key=secret_key, secure=secure)
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)[:200]

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "wired": self._client is not None,
            "bucket": self._ns.bucket() or os.getenv("MINIO_BUCKET", "agent-docs"),
            "prefix": self._ns.prefix(),
            "error": self._error,
        }

    def _bucket(self) -> str:
        return self._ns.bucket() or os.getenv("MINIO_BUCKET", "agent-docs").strip()

    async def put(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> DocumentRef:
        if self._client is None:
            raise RuntimeError(self._error or "minio not configured")
        import io

        bucket = self._bucket()
        key = self._ns.object_key(object_key)
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)
        self._client.put_object(bucket, key, io.BytesIO(content), length=len(content), content_type=content_type)
        return DocumentRef(
            bucket=bucket,
            object_key=key,
            checksum=hashlib.sha256(content).hexdigest(),
            content_type=content_type,
            size_bytes=len(content),
        )

    async def get(self, *, object_key: str) -> bytes:
        if self._client is None:
            raise RuntimeError(self._error or "minio not configured")
        key = self._ns.object_key(object_key) if not object_key.startswith(self._ns.prefix()) else object_key
        resp = self._client.get_object(self._bucket(), key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    async def exists(self, *, object_key: str) -> bool:
        if self._client is None:
            raise RuntimeError(self._error or "minio not configured")
        key = self._ns.object_key(object_key) if not object_key.startswith(self._ns.prefix()) else object_key
        try:
            self._client.stat_object(self._bucket(), key)
            return True
        except Exception:  # noqa: BLE001
            return False
