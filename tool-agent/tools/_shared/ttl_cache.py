from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")


class TtlCache(Generic[T]):
    """In-memory TTL cache with single-flight async refresh."""

    def __init__(self, *, ttl_seconds: float, enabled: bool = True) -> None:
        self._ttl_seconds = max(0.0, ttl_seconds)
        self._enabled = enabled
        self._data: T | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def is_fresh(self) -> bool:
        if not self._enabled or self._data is None:
            return False
        return time.monotonic() < self._expires_at

    def snapshot(self) -> T | None:
        return self._data if self.is_fresh() else None

    def age_seconds(self) -> float | None:
        if self._data is None or not self.is_fresh():
            return None
        return max(0.0, self._expires_at - time.monotonic())

    async def get_or_refresh(self, refresh_fn: Callable[[], Awaitable[T]]) -> T | None:
        if not self._enabled:
            return None
        if self.is_fresh():
            return self._data
        async with self._lock:
            if self.is_fresh():
                return self._data
            try:
                self._data = await refresh_fn()
                self._expires_at = time.monotonic() + self._ttl_seconds
            except Exception:
                return self._data
            return self._data

    def clear(self) -> None:
        self._data = None
        self._expires_at = 0.0
