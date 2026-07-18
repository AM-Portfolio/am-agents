"""Growth test: adding catalog YAML grows TargetSet; resolver code unchanged."""

from __future__ import annotations

from pathlib import Path

from am_platform_adapters.providers.spt import CatalogTargetResolver, FileTargetCatalog
from am_platform_ports.schemas.spt import SptSelector


def test_catalog_growth_increases_tag_expansion(tmp_path: Path) -> None:
    services = tmp_path / "services"
    services.mkdir()
    flows = tmp_path / "flows"
    flows.mkdir()
    (services / "tgt-x.yaml").write_text(
        "id: tgt-x\nkind: service\nenabled: true\ntags: [growth]\nscenario_ref: s1\n",
        encoding="utf-8",
    )
    r = CatalogTargetResolver(FileTargetCatalog(tmp_path))
    assert r.resolve(selector=SptSelector(tags=["growth"])) == ["tgt-x"]

    (services / "tgt-y.yaml").write_text(
        "id: tgt-y\nkind: service\nenabled: true\ntags: [growth]\nscenario_ref: s1\n",
        encoding="utf-8",
    )
    # new catalog instance picks up growth
    r2 = CatalogTargetResolver(FileTargetCatalog(tmp_path))
    assert set(r2.resolve(selector=SptSelector(tags=["growth"]))) == {"tgt-x", "tgt-y"}
