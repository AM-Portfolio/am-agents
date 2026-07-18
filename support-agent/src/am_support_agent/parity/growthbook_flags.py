"""Runtime GrowthBook feature flags with fail-closed route evaluation."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

from growthbook import GrowthBookClient, Options, UserContext


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True)
class FeatureFlagEvaluation:
    feature_key: str
    value: Any
    source: str
    ready: bool
    error: str = ""


class FeatureFlagProvider(Protocol):
    async def evaluate(
        self,
        feature_key: str,
        *,
        fallback: Any,
        attributes: dict[str, Any],
    ) -> FeatureFlagEvaluation: ...

    def status(self) -> dict[str, Any]: ...

    async def close(self) -> None: ...


class GrowthBookFeatureFlags:
    """One reusable async GrowthBook client for gateway runtime evaluation."""

    name = "growthbook"

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        api_host: str | None = None,
        client_key: str | None = None,
        cache_ttl: int | None = None,
    ) -> None:
        self.enabled = (
            _truthy("GROWTHBOOK_ENABLED", False) if enabled is None else enabled
        )
        self.api_host = (
            api_host
            or os.getenv("GROWTHBOOK_API_HOST", "").strip()
            or "https://api.growthbook.asrax.in"
        ).rstrip("/")
        self.client_key = (
            client_key
            if client_key is not None
            else os.getenv("GROWTHBOOK_CLIENT_KEY", "").strip()
        )
        self.cache_ttl = cache_ttl or _positive_int(
            "GROWTHBOOK_CACHE_TTL_SECONDS", 60
        )
        self.retry_seconds = _positive_int("GROWTHBOOK_RETRY_SECONDS", 30)
        self._client: GrowthBookClient | None = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._ready = False
        self._error = ""
        self._retry_at = 0.0

    async def _initialize(self) -> bool:
        if not self.enabled:
            return False
        if self._initialized and self._ready:
            return self._ready
        if time.monotonic() < self._retry_at:
            return False
        async with self._lock:
            if self._initialized and self._ready:
                return self._ready
            if time.monotonic() < self._retry_at:
                return False
            if not self.client_key:
                self._error = "GROWTHBOOK_CLIENT_KEY is not configured"
                self._retry_at = time.monotonic() + self.retry_seconds
                return False
            try:
                self._client = GrowthBookClient(
                    Options(
                        api_host=self.api_host,
                        client_key=self.client_key,
                        cache_ttl=self.cache_ttl,
                    )
                )
                self._ready = bool(await self._client.initialize())
                self._initialized = self._ready
                if not self._ready:
                    self._error = "GrowthBook SDK initialization returned false"
                    await self._client.close()
                    self._client = None
                    self._retry_at = time.monotonic() + self.retry_seconds
            except Exception as exc:  # noqa: BLE001
                self._error = str(exc)[:300]
                self._ready = False
                self._initialized = False
                if self._client is not None:
                    await self._client.close()
                    self._client = None
                self._retry_at = time.monotonic() + self.retry_seconds
            return self._ready

    async def evaluate(
        self,
        feature_key: str,
        *,
        fallback: Any,
        attributes: dict[str, Any],
    ) -> FeatureFlagEvaluation:
        if not self.enabled:
            return FeatureFlagEvaluation(
                feature_key=feature_key,
                value=fallback,
                source="environment",
                ready=False,
                error="GrowthBook disabled",
            )
        if not await self._initialize() or self._client is None:
            return FeatureFlagEvaluation(
                feature_key=feature_key,
                value=fallback,
                source=self.name,
                ready=False,
                error=self._error or "GrowthBook unavailable",
            )
        try:
            value = await self._client.get_feature_value(
                feature_key,
                fallback,
                UserContext(attributes=attributes),
            )
            return FeatureFlagEvaluation(
                feature_key=feature_key,
                value=value,
                source=self.name,
                ready=True,
            )
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)[:300]
            return FeatureFlagEvaluation(
                feature_key=feature_key,
                value=fallback,
                source=self.name,
                ready=False,
                error=self._error,
            )

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "configured": bool(self.client_key),
            "initialized": self._initialized,
            "ready": self._ready,
            "api_host": self.api_host,
            "cache_ttl_seconds": self.cache_ttl,
            "retry_seconds": self.retry_seconds,
            "route_feature_key": os.getenv(
                "GROWTHBOOK_ROUTE_FEATURE_KEY", "support-agent-route"
            ),
            "error": self._error,
        }

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        self._ready = False


def build_feature_flags() -> GrowthBookFeatureFlags:
    return GrowthBookFeatureFlags()


__all__ = [
    "FeatureFlagEvaluation",
    "FeatureFlagProvider",
    "GrowthBookFeatureFlags",
    "build_feature_flags",
]
