"""DocStore / FailoverDocStore unit tests."""

from __future__ import annotations

from am_platform_adapters.failover_docstore import FailoverDocStore
from am_platform_ports.fakes import FakeDocStore
from am_platform_ports.schemas.core import DocRef


class _FailingPrimary:
    def put(self, *, key: str, content: bytes, content_type: str = "application/octet-stream", meta=None):
        raise ConnectionError("minio down")

    def get(self, *, docs_ref: str) -> bytes:
        raise KeyError(docs_ref)

    def exists(self, *, docs_ref: str) -> bool:
        return False


def test_fake_doc_store_roundtrip() -> None:
    store = FakeDocStore()
    ref = store.put(key="runs/r1/note.md", content=b"# hello", content_type="text/markdown")
    assert ref.provider == "fake"
    assert ref.docs_ref.startswith("fake:")
    assert store.get(docs_ref=ref.docs_ref) == b"# hello"
    assert store.exists(docs_ref=ref.docs_ref)


def test_failover_uses_fallback_on_connection_error() -> None:
    fallback = FakeDocStore()
    store = FailoverDocStore(primary=_FailingPrimary(), fallback=fallback)
    ref = store.put(key="x.txt", content=b"ok")
    assert ref.provider == "fake"
    assert fallback.get(docs_ref=ref.docs_ref) == b"ok"


def test_failover_primary_success_no_fallback_write() -> None:
    primary = FakeDocStore()
    fallback = FakeDocStore()
    store = FailoverDocStore(primary=primary, fallback=fallback)
    ref = store.put(key="only-primary.txt", content=b"p")
    assert ref.docs_ref in primary.objects
    assert fallback.objects == {}


def test_factory_doc_store_fake(monkeypatch) -> None:
    monkeypatch.setenv("DOC_PROVIDER", "fake")
    monkeypatch.delenv("DOC_FALLBACK", raising=False)
    from am_platform_adapters import factory as af

    store = af.build_doc_store()
    assert store.__class__.__name__ == "FakeDocStore"
