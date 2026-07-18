"""SPT runaway / prod policy guards."""

from __future__ import annotations

from pathlib import Path

import pytest

from am_platform_adapters.providers.spt import (
    CatalogTargetResolver,
    FileTargetCatalog,
    LabLoadPolicy,
    ProdLoadPolicy,
)
from am_platform_ports.schemas.spt import SptDemandRequest, SptSelector

ROOT = Path(__file__).resolve().parents[3] / "catalog" / "spt"


def test_resolver_max_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPT_MAX_TARGETS_PER_RUN", "1")
    r = CatalogTargetResolver(FileTargetCatalog(ROOT))
    with pytest.raises(PermissionError, match="expanded_count"):
        r.resolve(selector=SptSelector(ids=["tgt-a", "tgt-b"]))


def test_selector_all_requires_lab_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPT_ENV", "lab")
    monkeypatch.delenv("SPT_ALLOW_ALL", raising=False)
    r = CatalogTargetResolver(FileTargetCatalog(ROOT))
    with pytest.raises(PermissionError, match="SPT_ALLOW_ALL"):
        r.resolve(selector=SptSelector(all=True))


def test_selector_all_blocked_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPT_ENV", "prod")
    monkeypatch.setenv("SPT_ALLOW_ALL", "1")
    r = CatalogTargetResolver(FileTargetCatalog(ROOT))
    with pytest.raises(PermissionError, match="only allowed in lab"):
        r.resolve(selector=SptSelector(all=True))


def test_prod_policy_requires_approve_and_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPT_CATALOG_PATH", str(ROOT))
    # FileTargetCatalog uses SPT_CATALOG_PATH or default — ensure lab catalog
    req = SptDemandRequest(demand_ref="d1", selector=SptSelector(ids=["tgt-a"]))
    pol = ProdLoadPolicy()
    monkeypatch.delenv("SPT_APPROVED", raising=False)
    monkeypatch.delenv("SPT_CHANGE_WINDOW_OPEN", raising=False)
    assert pol.allow(target_ref="tgt-a", request=req) is False
    monkeypatch.setenv("SPT_APPROVED", "1")
    assert pol.allow(target_ref="tgt-a", request=req) is False
    monkeypatch.setenv("SPT_CHANGE_WINDOW_OPEN", "1")
    # ProdLoadPolicy constructs FileTargetCatalog() which needs path
    monkeypatch.setenv("SPT_CATALOG_PATH", str(ROOT))
    assert pol.allow(target_ref="tgt-a", request=req) is True


def test_lab_policy_enabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPT_CATALOG_PATH", str(ROOT))
    req = SptDemandRequest(demand_ref="d1", selector=SptSelector(ids=["tgt-a"]))
    assert LabLoadPolicy().allow(target_ref="tgt-a", request=req) is True
