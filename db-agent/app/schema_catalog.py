from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.config import AGENT_ROOT

logger = logging.getLogger(__name__)

CATALOG_PATH = AGENT_ROOT / "config" / "schema_catalog.yaml"
_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


@dataclass(frozen=True)
class EntityMapping:
    name: str
    backend: str
    database: str | None = None
    collection: str | None = None
    schema: str | None = None
    table: str | None = None
    id_field: str = "_id"
    alternate_id_fields: tuple[str, ...] = ()
    key_template: str | None = None
    key_pattern: str | None = None
    lookup_fields: dict[str, str] = field(default_factory=dict)


class SchemaCatalog:
    def __init__(self, data: dict[str, Any]) -> None:
        self._environment = str(data.get("environment") or "default")
        self._defaults: dict[str, dict[str, str]] = dict(data.get("defaults") or {})
        self._entities: dict[str, EntityMapping] = {}
        for name, cfg in (data.get("entities") or {}).items():
            if not isinstance(cfg, dict):
                continue
            self._entities[str(name)] = EntityMapping(
                name=str(name),
                backend=str(cfg.get("backend") or ""),
                database=cfg.get("database"),
                collection=cfg.get("collection"),
                schema=cfg.get("schema"),
                table=cfg.get("table"),
                id_field=str(cfg.get("id_field") or "_id"),
                alternate_id_fields=tuple(cfg.get("alternate_id_fields") or ()),
                key_template=cfg.get("key_template"),
                key_pattern=cfg.get("key_pattern"),
                lookup_fields=dict(cfg.get("lookup_fields") or {}),
            )

    @property
    def environment(self) -> str:
        return self._environment

    def entity(self, name: str) -> EntityMapping | None:
        return self._entities.get(name)

    def entities_for_backend(self, backend: str) -> list[EntityMapping]:
        return [m for m in self._entities.values() if m.backend == backend]

    def default_for(self, backend: str, key: str) -> str | None:
        backend_defaults = self._defaults.get(backend) or {}
        value = backend_defaults.get(key)
        return str(value) if value else None

    def default_database(self, backend: str) -> str | None:
        return self.default_for(backend, "database")

    def catalog_snippet(self) -> str:
        lines = ["Known entities (use params.entity + params.id when location omitted):"]
        for mapping in self._entities.values():
            parts = [f"- {mapping.name}: backend={mapping.backend}"]
            if mapping.database:
                parts.append(f"database={mapping.database}")
            if mapping.collection:
                parts.append(f"collection={mapping.collection}")
            if mapping.schema and mapping.table:
                parts.append(f"table={mapping.schema}.{mapping.table}")
            elif mapping.table:
                parts.append(f"table={mapping.table}")
            if mapping.key_pattern:
                parts.append(f"key_pattern={mapping.key_pattern}")
            if mapping.id_field != "_id":
                parts.append(f"id_field={mapping.id_field}")
            if mapping.lookup_fields:
                parts.append(f"lookup_fields={','.join(mapping.lookup_fields.keys())}")
            lines.append(", ".join(parts))
        for backend in ("mongodb", "postgres", "redis"):
            defaults = self._defaults.get(backend) or {}
            if defaults:
                pairs = ", ".join(f"{k}={v}" for k, v in defaults.items())
                lines.append(f"Default {backend}: {pairs}")
        return "\n".join(lines)


_catalog: SchemaCatalog | None = None


def _load_catalog() -> SchemaCatalog:
    if not CATALOG_PATH.exists():
        logger.warning("schema catalog missing at %s", CATALOG_PATH)
        return SchemaCatalog({})
    with CATALOG_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return SchemaCatalog(data)


def get_schema_catalog() -> SchemaCatalog:
    global _catalog
    if _catalog is None:
        _catalog = _load_catalog()
    return _catalog


def reset_schema_catalog() -> None:
    global _catalog
    _catalog = None


def qualified_pg_table(mapping: EntityMapping) -> str:
    schema = mapping.schema or "public"
    table = mapping.table or mapping.name
    if not _IDENT_RE.match(schema) or not _IDENT_RE.match(table):
        raise ValueError(f"Invalid postgres identifier: {schema}.{table}")
    return f'"{schema}"."{table}"'


def postgres_select_sql(mapping: EntityMapping, entity_id: str, *, limit: int = 100) -> str:
    return postgres_select_by_field(mapping, mapping.id_field, entity_id, limit=limit)


def postgres_select_by_field(
    mapping: EntityMapping,
    column: str,
    value: str,
    *,
    limit: int = 100,
) -> str:
    if not _IDENT_RE.match(column):
        raise ValueError(f"Invalid postgres column: {column}")
    safe_value = value.replace("'", "''")
    return (
        f"SELECT * FROM {qualified_pg_table(mapping)} "
        f"WHERE \"{column}\" = '{safe_value}' LIMIT {limit}"
    )
