"""SPT catalog / resolver unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from am_platform_adapters.providers.spt import (
    CatalogTargetResolver,
    DedupeDataPrep,
    FileTargetCatalog,
)
from am_platform_ports.schemas.spt import SptSelector

ROOT = Path(__file__).resolve().parents[3] / "catalog" / "spt"


def test_catalog_lists_lab_services() -> None:
    cat = FileTargetCatalog(ROOT)
    services = cat.list_services()
    assert len(services) >= 3
    ids = {s["id"] for s in services}
    assert {"tgt-a", "tgt-b", "tgt-c"} <= ids
    # shared prep
    assert cat.get(target_id="tgt-a")["prep_ref"] == cat.get(target_id="tgt-b")["prep_ref"]
    assert cat.get(target_id="tgt-c").get("prep_ref") in (None, "")


def test_resolver_by_ids_and_tags() -> None:
    r = CatalogTargetResolver(FileTargetCatalog(ROOT))
    ids = r.resolve(selector=SptSelector(ids=["tgt-a", "tgt-c"]))
    assert ids == ["tgt-a", "tgt-c"]
    tagged = r.resolve(selector=SptSelector(tags=["tier-1"]))
    assert set(tagged) == {"tgt-a", "tgt-b"}


def test_resolver_empty_fatal() -> None:
    r = CatalogTargetResolver(FileTargetCatalog(ROOT))
    with pytest.raises(ValueError, match="empty TargetSet"):
        r.resolve(selector=SptSelector(tags=["no-such-tag-zzz"]))


def test_prep_dedupe_per_parent() -> None:
    prep = DedupeDataPrep()
    a = prep.ensure_dataset(prep_ref="prep.shared-lab", parent_run_ref="run-1")
    b = prep.ensure_dataset(prep_ref="prep.shared-lab", parent_run_ref="run-1")
    c = prep.ensure_dataset(prep_ref="prep.shared-lab", parent_run_ref="run-2")
    assert a == b
    assert a != c
