from __future__ import annotations

import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class PostgresAdapter:
    @property
    def available(self) -> bool:
        return bool(settings.POSTGRES_URL)

    async def execute(
        self, operation: str, params: dict[str, Any], *, read_only: bool, max_rows: int
    ) -> Any:
        if not settings.POSTGRES_URL:
            raise RuntimeError("Postgres not configured (set POSTGRES_URL)")

        try:
            import asyncpg
        except ImportError as exc:
            raise RuntimeError("asyncpg not installed") from exc

        conn = await asyncpg.connect(settings.POSTGRES_URL)
        try:
            if operation == "run_sql":
                sql = str(params.get("sql", "")).strip()
                if not sql:
                    raise ValueError("sql required")
                if not sql.upper().startswith("SELECT"):
                    raise ValueError("Only SELECT allowed via adapter")
                rows = await conn.fetch(sql)
                data = [dict(r) for r in rows[:max_rows]]
                return {"rows": data, "count": len(data)}

            if operation == "table_row_count":
                table = params.get("table")
                if not table:
                    raise ValueError("table required")
                if "." in str(table):
                    schema_name, table_name = str(table).split(".", 1)
                    if not _IDENT_RE.match(schema_name) or not _IDENT_RE.match(table_name):
                        raise ValueError("invalid table identifier")
                    qualified = f'"{schema_name}"."{table_name}"'
                else:
                    schema_name = str(params.get("schema", "public"))
                    table_name = str(table)
                    if not _IDENT_RE.match(schema_name) or not _IDENT_RE.match(table_name):
                        raise ValueError("invalid table identifier")
                    qualified = f'"{schema_name}"."{table_name}"'
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {qualified}")
                return {"schema": schema_name, "table": table_name, "count": count}

            if operation == "search_schema":
                pattern = params.get("pattern", "%")
                rows = await conn.fetch(
                    """
                    SELECT table_schema, table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name ILIKE $1 OR column_name ILIKE $1
                    LIMIT $2
                    """,
                    pattern,
                    max_rows,
                )
                return {"matches": [dict(r) for r in rows]}

            raise ValueError(f"Unsupported Postgres operation: {operation}")
        finally:
            await conn.close()
