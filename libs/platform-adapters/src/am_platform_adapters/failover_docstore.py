"""FailoverDocStore — try primary; on retryable failure use fallback (no dual-write)."""

from __future__ import annotations

import logging
from typing import Any

from am_platform_ports.ports.docs import DocStore
from am_platform_ports.schemas.core import DocRef

LOG = logging.getLogger("am_platform_adapters.failover_docstore")

# Errors that warrant failover (not auth / not-found on get)
_RETRYABLE = (
    ConnectionError,
    TimeoutError,
    OSError,
)


class FailoverDocStore:
    """
    Primary first (MinIO). If put fails with a retryable error and fallback is set,
    write to fallback once. ``docs_ref`` sticks to whichever provider succeeded.
    """

    def __init__(self, *, primary: DocStore, fallback: DocStore | None = None) -> None:
        self._primary = primary
        self._fallback = fallback

    def put(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        meta: dict[str, str] | None = None,
    ) -> DocRef:
        try:
            return self._primary.put(
                key=key, content=content, content_type=content_type, meta=meta
            )
        except Exception as exc:
            if self._fallback is None or not _is_retryable(exc):
                raise
            LOG.warning("DocStore primary failed (%s); failing over", exc.__class__.__name__)
            return self._fallback.put(
                key=key, content=content, content_type=content_type, meta=meta
            )

    def get(self, *, docs_ref: str) -> bytes:
        store = self._store_for_ref(docs_ref)
        return store.get(docs_ref=docs_ref)

    def exists(self, *, docs_ref: str) -> bool:
        store = self._store_for_ref(docs_ref)
        return store.exists(docs_ref=docs_ref)

    def _store_for_ref(self, docs_ref: str) -> DocStore:
        if docs_ref.startswith("minio:") or docs_ref.startswith("fake:"):
            return self._primary
        if docs_ref.startswith("gdrive:") and self._fallback is not None:
            return self._fallback
        # Prefer primary; if missing try fallback
        if self._primary.exists(docs_ref=docs_ref):
            return self._primary
        if self._fallback is not None:
            return self._fallback
        return self._primary


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, _RETRYABLE):
        return True
    name = exc.__class__.__name__.lower()
    msg = str(exc).lower()
    needles = ("timeout", "connection", "unavailable", "reset", "refused", "broken pipe")
    return any(n in name or n in msg for n in needles)
