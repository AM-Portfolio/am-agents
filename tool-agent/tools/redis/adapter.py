from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)


class RedisAdapter:
    def __init__(self) -> None:
        self._url = settings.REDIS_URL

    @property
    def available(self) -> bool:
        return bool(self._url)

    async def _client(self) -> aioredis.Redis:
        if not self._url:
            raise RuntimeError("Redis not configured (set REDIS_URL)")
        return aioredis.from_url(self._url, decode_responses=True)

    async def execute(
        self, operation: str, params: dict[str, Any], *, read_only: bool, max_rows: int
    ) -> Any:
        client = await self._client()
        try:
            if operation == "scan_keys":
                pattern = str(params.get("pattern", "*"))
                keys: list[str] = []
                async for key in client.scan_iter(match=pattern, count=100):
                    keys.append(key)
                    if len(keys) >= max_rows:
                        break
                return {"pattern": pattern, "keys": keys, "count": len(keys)}

            if operation == "get":
                key = params.get("key")
                if not key:
                    raise ValueError("key required")
                val = await client.get(str(key))
                return {"key": key, "value": val}

            if operation == "info":
                section = params.get("section")
                if section:
                    info = await client.info(section=str(section))
                else:
                    info = await client.info()
                return {"info": info}

            if operation == "type":
                key = params.get("key")
                if not key:
                    raise ValueError("key required")
                key_type = await client.type(str(key))
                return {"key": key, "type": key_type}

            raise ValueError(f"Unsupported Redis operation: {operation}")
        finally:
            await client.aclose()
