from __future__ import annotations

import base64
import io
import os
from typing import Any
from urllib.parse import urlparse


class Adapter:
    def __init__(self) -> None:
        self._client = None
        self._bucket = (os.environ.get("MINIO_BUCKET") or "agent-docs").strip()
        endpoint = (os.environ.get("MINIO_ENDPOINT") or "").strip()
        access_key = (os.environ.get("MINIO_ACCESS_KEY") or "").strip()
        secret_key = (os.environ.get("MINIO_SECRET_KEY") or "").strip()
        if not (endpoint and access_key and secret_key):
            return
        try:
            from minio import Minio
        except ImportError:
            return
        parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        host = parsed.hostname or endpoint
        port = parsed.port
        secure = parsed.scheme == "https"
        endpoint_host = f"{host}:{port}" if port else host
        self._client = Minio(endpoint_host, access_key=access_key, secret_key=secret_key, secure=secure)

    @property
    def available(self) -> bool:
        return self._client is not None

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        assert self._client is not None
        bucket = str(params.get("bucket") or self._bucket)
        key = str(params.get("object_key") or params.get("key") or "").lstrip("/")
        if operation == "put":
            content = params.get("content")
            if isinstance(content, str):
                raw = base64.b64decode(content) if params.get("content_encoding") == "base64" else content.encode()
            else:
                raw = bytes(content or b"")
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)
            self._client.put_object(
                bucket,
                key,
                io.BytesIO(raw),
                length=len(raw),
                content_type=str(params.get("content_type") or "application/octet-stream"),
            )
            return {"docs_ref": f"minio:{bucket}/{key}", "bucket": bucket, "object_key": key, "size_bytes": len(raw)}
        if operation == "get":
            resp = self._client.get_object(bucket, key)
            try:
                raw = resp.read()
            finally:
                resp.close()
                resp.release_conn()
            return {
                "docs_ref": f"minio:{bucket}/{key}",
                "content_base64": base64.b64encode(raw).decode("ascii"),
            }
        if operation == "exists":
            try:
                self._client.stat_object(bucket, key)
                exists = True
            except Exception:
                exists = False
            return {"exists": exists, "docs_ref": f"minio:{bucket}/{key}"}
        if operation == "signed-url.create":
            from datetime import timedelta

            url = self._client.presigned_get_object(bucket, key, expires=timedelta(hours=1))
            return {"url": url, "docs_ref": f"minio:{bucket}/{key}", "expires_in": 3600}
        raise ValueError(operation)
