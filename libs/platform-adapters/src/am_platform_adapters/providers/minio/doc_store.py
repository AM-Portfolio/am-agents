"""MinIO DocStore — S3-compatible primary storage."""

from __future__ import annotations

import io
import os
from urllib.parse import urlparse

from am_platform_ports.schemas.core import DocRef


def _parse_docs_ref(docs_ref: str) -> tuple[str, str]:
    """``minio:{bucket}/{object_key}`` → bucket, key."""
    if not docs_ref.startswith("minio:"):
        raise ValueError(f"not a minio docs_ref: {docs_ref!r}")
    rest = docs_ref[len("minio:") :]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError(f"invalid minio docs_ref: {docs_ref!r}")
    return bucket, key


class MinioDocStore:
    """Put/get objects in a MinIO bucket. ``docs_ref`` = ``minio:{bucket}/{key}``."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        secure: bool | None = None,
    ) -> None:
        endpoint = (endpoint or os.environ.get("MINIO_ENDPOINT", "")).strip()
        access_key = (access_key or os.environ.get("MINIO_ACCESS_KEY", "")).strip()
        secret_key = (secret_key or os.environ.get("MINIO_SECRET_KEY", "")).strip()
        self._bucket = (bucket or os.environ.get("MINIO_BUCKET", "agent-docs")).strip()
        if not endpoint or not access_key or not secret_key:
            raise RuntimeError("MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY required")

        parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        host = parsed.hostname or endpoint
        port = parsed.port
        self._secure = secure if secure is not None else parsed.scheme == "https"
        self._endpoint_host = f"{host}:{port}" if port else host

        try:
            from minio import Minio
        except ImportError as exc:
            raise RuntimeError(
                "minio package required for DOC_PROVIDER=minio — pip install minio"
            ) from exc

        self._client = Minio(
            self._endpoint_host,
            access_key=access_key,
            secret_key=secret_key,
            secure=self._secure,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    def put(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        meta: dict[str, str] | None = None,
    ) -> DocRef:
        object_key = key.lstrip("/")
        self._client.put_object(
            self._bucket,
            object_key,
            io.BytesIO(content),
            length=len(content),
            content_type=content_type,
            metadata=meta or {},
        )
        docs_ref = f"minio:{self._bucket}/{object_key}"
        scheme = "https" if self._secure else "http"
        url = f"{scheme}://{self._endpoint_host}/{self._bucket}/{object_key}"
        return DocRef(docs_ref=docs_ref, provider="minio", url=url, key=object_key)

    def get(self, *, docs_ref: str) -> bytes:
        bucket, object_key = _parse_docs_ref(docs_ref)
        resp = self._client.get_object(bucket, object_key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def exists(self, *, docs_ref: str) -> bool:
        from minio.error import S3Error

        bucket, object_key = _parse_docs_ref(docs_ref)
        try:
            self._client.stat_object(bucket, object_key)
            return True
        except S3Error:
            return False
