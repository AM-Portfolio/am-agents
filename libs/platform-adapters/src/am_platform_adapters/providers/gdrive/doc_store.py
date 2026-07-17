"""GDrive DocStore stub — Phase 2 failover target (not dual-write)."""

from __future__ import annotations

from am_platform_ports.schemas.core import DocRef


class GDriveDocStore:
    """Placeholder until Google Drive credentials are wired."""

    def put(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        meta: dict[str, str] | None = None,
    ) -> DocRef:
        raise NotImplementedError(
            "DOC_FALLBACK=gdrive not configured yet — set GDrive creds or unset DOC_FALLBACK"
        )

    def get(self, *, docs_ref: str) -> bytes:
        raise NotImplementedError("GDrive DocStore.get not implemented")

    def exists(self, *, docs_ref: str) -> bool:
        return False
