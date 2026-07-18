from __future__ import annotations

import base64
import hashlib
from typing import Any


class MemoryAdapter:
    _objects: dict[str, dict[str, Any]] = {}

    @property
    def available(self) -> bool:
        return True

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        key = str(params.get("object_key") or params.get("key") or "").lstrip("/")
        bucket = str(params.get("bucket") or "memory")
        ref = f"memory:{bucket}/{key}"
        if operation == "put":
            content = params.get("content")
            if isinstance(content, str):
                raw = base64.b64decode(content) if params.get("content_encoding") == "base64" else content.encode()
            else:
                raw = bytes(content or b"")
            checksum = hashlib.sha256(raw).hexdigest()
            self._objects[ref] = {
                "content": raw,
                "content_type": params.get("content_type") or "application/octet-stream",
                "checksum": checksum,
            }
            return {"object_key": key, "bucket": bucket, "checksum": checksum, "docs_ref": ref, "size_bytes": len(raw)}
        if operation == "get":
            obj = self._objects.get(ref) or self._objects.get(str(params.get("docs_ref") or ""))
            if not obj:
                raise KeyError(f"document not found: {ref}")
            return {
                "docs_ref": ref,
                "content_base64": base64.b64encode(obj["content"]).decode("ascii"),
                "content_type": obj["content_type"],
                "checksum": obj["checksum"],
            }
        if operation == "exists":
            exists = ref in self._objects or str(params.get("docs_ref") or "") in self._objects
            return {"exists": exists, "docs_ref": ref}
        if operation == "signed-url.create":
            return {"url": f"memory://{bucket}/{key}", "docs_ref": ref, "expires_in": 3600}
        raise ValueError(operation)
