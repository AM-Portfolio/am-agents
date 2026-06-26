from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from app.config import settings, TOOLS_DIR
from tools._loader import get_enabled_tools

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
    def __init__(self) -> None:
        self.environment = settings.APP_ENV
        self._entities: dict[str, EntityMapping] = {}
        self._defaults: dict[str, dict[str, str]] = {}
        self._databases: dict[str, dict[str, dict[str, Any]]] = {}
        self._vault_categories: dict[str, dict[str, Any]] = {}
        self._vault_path_aliases: dict[str, str] = {}
        self._kafka_topic_aliases: dict[str, str] = {}
        self._load_all()

    def _schema_file(self, tool_dir) -> Any:
        for name in (settings.APP_ENV, "preprod", "defaults"):
            path = tool_dir / "schema" / f"{name}.yaml"
            if path.exists():
                return path
        return None

    def _load_all(self) -> None:
        for tool in get_enabled_tools():
            if not tool.manifest.has_entities:
                continue
            path = self._schema_file(tool.tool_dir)
            if not path:
                continue
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            backend = tool.name
            self._defaults[backend] = {str(k): str(v) for k, v in (data.get("defaults") or {}).items()}
            db_catalog: dict[str, dict[str, Any]] = {}
            for db_name, cfg in (data.get("databases") or {}).items():
                if isinstance(cfg, dict):
                    db_catalog[str(db_name)] = cfg
            if db_catalog:
                self._databases[backend] = db_catalog
            for entity_name, cfg in (data.get("entities") or {}).items():
                if not isinstance(cfg, dict):
                    continue
                self._entities[str(entity_name)] = EntityMapping(
                    name=str(entity_name),
                    backend=backend,
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
            if backend == "vault":
                self._vault_categories = dict(data.get("categories") or {})
                self._vault_path_aliases = {
                    str(k).lower(): str(v) for k, v in (data.get("path_aliases") or {}).items()
                }
            if backend == "kafka":
                self._kafka_topic_aliases = {
                    str(k).lower(): str(v) for k, v in (data.get("topic_aliases") or {}).items()
                }

    def entity(self, name: str) -> EntityMapping | None:
        return self._entities.get(name)

    def entities_for_backend(self, backend: str) -> list[EntityMapping]:
        return [m for m in self._entities.values() if m.backend == backend]

    def default_for(self, backend: str, key: str) -> str | None:
        value = (self._defaults.get(backend) or {}).get(key)
        return str(value) if value else None

    def default_database(self, backend: str) -> str | None:
        return self.default_for(backend, "database")

    def vault_path_alias(self, token: str) -> str | None:
        return self._vault_path_aliases.get(token.lower())

    def vault_categories(self) -> dict[str, dict[str, Any]]:
        return self._vault_categories

    def vault_infra_components(self) -> list[str]:
        infra = self._vault_categories.get("infra") or {}
        leaves = infra.get("known_leaves") or []
        return [str(leaf) for leaf in leaves]

    def vault_category_default_leaf(self, category: str) -> str | None:
        cfg = self._vault_categories.get(category) or {}
        leaf = cfg.get("default_leaf")
        return str(leaf) if leaf else None

    def kafka_topic_alias(self, name: str) -> str | None:
        return self._kafka_topic_aliases.get(name.lower())

    def snippet(self, backends: list[str] | None = None) -> str:
        lines = ["Known entities (use params.entity + params.id when location omitted):"]
        for mapping in self._entities.values():
            if backends and mapping.backend not in backends:
                continue
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
            lines.append(", ".join(parts))
        if not backends or "vault" in backends:
            mount = self.default_for("vault", "mount") or "apps"
            lines.append(
                f"Vault mount `{mount}` — convention preprod/{{infra|services|api}}/{{leaf}} "
                f"(MCP path without apps/ prefix). Infra leaves: "
                f"{', '.join(self.vault_infra_components()) or 'postgres, mongodb, redis, kafka'}. "
                f"Services: am-* naming. Use list_secrets for discovery."
            )
            if self._vault_path_aliases:
                sample = ", ".join(f"{k}→{v}" for k, v in list(self._vault_path_aliases.items())[:8])
                lines.append(f"Vault typo aliases: {sample}, ...")
        if not backends or "kafka" in backends:
            lines.append(
                "Kafka topics: naming convention am-*, dashboard-*, *.DLQ — "
                "use list_topics or entity params (portfolio_stream, trade_update, ...)."
            )
            if self._kafka_topic_aliases:
                sample = ", ".join(f"{k}→{v}" for k, v in list(self._kafka_topic_aliases.items())[:6])
                lines.append(f"Kafka legacy aliases: {sample}, ...")
        for backend in ("mongodb", "postgres", "redis", "qdrant"):
            if backends and backend not in backends:
                continue
            defaults = self._defaults.get(backend) or {}
            if defaults:
                pairs = ", ".join(f"{k}={v}" for k, v in defaults.items())
                lines.append(f"Default {backend}: {pairs}")
            for db_name, cfg in (self._databases.get(backend) or {}).items():
                collections = cfg.get("collections") or []
                if collections:
                    coll_text = ", ".join(str(c) for c in collections)
                    lines.append(f"Database {backend}.{db_name}: collections=[{coll_text}]")
        return "\n".join(lines) if len(lines) > 1 else "(no entity mappings loaded)"


def qualified_pg_table(mapping: EntityMapping) -> str:
    schema = mapping.schema or "public"
    table = mapping.table or mapping.name
    if not _IDENT_RE.match(schema) or not _IDENT_RE.match(table):
        raise ValueError(f"Invalid postgres identifier: {schema}.{table}")
    return f'"{schema}"."{table}"'


def postgres_select_by_field(mapping: EntityMapping, column: str, value: str, *, limit: int = 100) -> str:
    if not _IDENT_RE.match(column):
        raise ValueError(f"Invalid postgres column: {column}")
    safe_value = value.replace("'", "''")
    return (
        f"SELECT * FROM {qualified_pg_table(mapping)} "
        f"WHERE \"{column}\" = '{safe_value}' LIMIT {limit}"
    )


def postgres_select_sql(mapping: EntityMapping, entity_id: str, *, limit: int = 100) -> str:
    return postgres_select_by_field(mapping, mapping.id_field, entity_id, limit=limit)


_catalog: SchemaCatalog | None = None


def get_schema_catalog() -> SchemaCatalog:
    global _catalog
    if _catalog is None:
        _catalog = SchemaCatalog()
    return _catalog


def reset_schema_catalog() -> None:
    global _catalog
    _catalog = None
