"""Canary routing — legacy remains default until explicitly selected."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from am_support_agent.parity.growthbook_flags import FeatureFlagProvider


class CanaryMode(str, Enum):
    OFF = "off"
    SHADOW = "shadow"
    CANARY = "canary"


class RouteTarget(str, Enum):
    LEGACY = "legacy"
    SUPPORT = "support"
    SHADOW = "shadow"


@dataclass(frozen=True)
class CanaryDecision:
    mode: CanaryMode
    route: RouteTarget
    reason: str
    percent: int
    allowlisted: bool
    key: str
    source: str = "environment"
    feature_key: str = ""
    flag_value: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "route": self.route.value,
            "reason": self.reason,
            "percent": self.percent,
            "allowlisted": self.allowlisted,
            "key": self.key,
            "source": self.source,
            "feature_key": self.feature_key,
            "flag_value": self.flag_value,
            "rollback": self.route == RouteTarget.LEGACY,
        }


def _parse_mode(raw: str) -> CanaryMode:
    value = (raw or "off").strip().lower()
    if value in {"shadow", "mirror"}:
        return CanaryMode.SHADOW
    if value in {"canary", "on"}:
        return CanaryMode.CANARY
    return CanaryMode.OFF


def _parse_percent(raw: str) -> int:
    try:
        return max(0, min(100, int(str(raw).strip() or "0")))
    except ValueError:
        return 0


def _allowlist() -> set[str]:
    raw = os.getenv("SUPPORT_AGENT_CANARY_ALLOWLIST", "") or ""
    return {part.strip() for part in raw.split(",") if part.strip()}


def _sticky_bucket(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def canary_config() -> dict[str, Any]:
    mode = _parse_mode(os.getenv("SUPPORT_AGENT_CANARY_MODE", "off"))
    percent = _parse_percent(os.getenv("SUPPORT_AGENT_CANARY_PERCENT", "0"))
    force_legacy = os.getenv("SUPPORT_AGENT_FORCE_LEGACY", "").lower() in {
        "1",
        "true",
        "yes",
    }
    return {
        "mode": mode.value,
        "percent": percent,
        "allowlist_count": len(_allowlist()),
        "force_legacy": force_legacy,
        "default_route": RouteTarget.LEGACY.value,
        "rollback": "set SUPPORT_AGENT_FORCE_LEGACY=true or SUPPORT_AGENT_CANARY_MODE=off",
    }


def decide_route(key: str = "") -> CanaryDecision:
    """Decide whether traffic may use support-agent (vs legacy default)."""
    normalized = (key or "").strip() or "anonymous"
    force_legacy = os.getenv("SUPPORT_AGENT_FORCE_LEGACY", "").lower() in {
        "1",
        "true",
        "yes",
    }
    mode = _parse_mode(os.getenv("SUPPORT_AGENT_CANARY_MODE", "off"))
    percent = _parse_percent(os.getenv("SUPPORT_AGENT_CANARY_PERCENT", "0"))
    allowlisted = normalized in _allowlist()

    if force_legacy:
        return CanaryDecision(
            mode=mode,
            route=RouteTarget.LEGACY,
            reason="force_legacy",
            percent=percent,
            allowlisted=allowlisted,
            key=normalized,
        )

    if mode == CanaryMode.OFF:
        return CanaryDecision(
            mode=mode,
            route=RouteTarget.LEGACY,
            reason="canary_off",
            percent=percent,
            allowlisted=allowlisted,
            key=normalized,
        )

    if mode == CanaryMode.SHADOW:
        return CanaryDecision(
            mode=mode,
            route=RouteTarget.SHADOW,
            reason="shadow_mirror_only",
            percent=percent,
            allowlisted=allowlisted,
            key=normalized,
        )

    # canary
    if allowlisted:
        return CanaryDecision(
            mode=mode,
            route=RouteTarget.SUPPORT,
            reason="allowlist",
            percent=percent,
            allowlisted=True,
            key=normalized,
        )
    if percent <= 0:
        return CanaryDecision(
            mode=mode,
            route=RouteTarget.LEGACY,
            reason="percent_zero",
            percent=percent,
            allowlisted=False,
            key=normalized,
        )
    if _sticky_bucket(normalized) < percent:
        return CanaryDecision(
            mode=mode,
            route=RouteTarget.SUPPORT,
            reason="percent_bucket",
            percent=percent,
            allowlisted=False,
            key=normalized,
        )
    return CanaryDecision(
        mode=mode,
        route=RouteTarget.LEGACY,
        reason="percent_miss",
        percent=percent,
        allowlisted=False,
        key=normalized,
    )


def _route_from_flag(value: Any) -> RouteTarget:
    if value is True:
        return RouteTarget.SUPPORT
    if value is False or value is None:
        return RouteTarget.LEGACY
    normalized = str(value).strip().lower()
    if normalized in {"support", "new", "v2", "on", "enabled", "true"}:
        return RouteTarget.SUPPORT
    if normalized in {"shadow", "mirror"}:
        return RouteTarget.SHADOW
    return RouteTarget.LEGACY


async def decide_route_runtime(
    key: str,
    *,
    feature_flags: FeatureFlagProvider,
    attributes: dict[str, Any] | None = None,
) -> CanaryDecision:
    """Use GrowthBook when enabled; otherwise preserve environment routing."""
    normalized = (key or "").strip() or "anonymous"
    if os.getenv("SUPPORT_AGENT_FORCE_LEGACY", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        return CanaryDecision(
            mode=CanaryMode.OFF,
            route=RouteTarget.LEGACY,
            reason="force_legacy",
            percent=0,
            allowlisted=False,
            key=normalized,
            source="environment",
        )

    if not feature_flags.status().get("enabled"):
        return decide_route(normalized)

    feature_key = os.getenv(
        "GROWTHBOOK_ROUTE_FEATURE_KEY", "support-agent-route"
    ).strip()
    context = {
        "id": normalized,
        "key": normalized,
        "environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "unknown"),
        "service": "support-agent",
        **(attributes or {}),
    }
    evaluation = await feature_flags.evaluate(
        feature_key,
        fallback="legacy",
        attributes=context,
    )
    route = _route_from_flag(evaluation.value)
    mode = CanaryMode.SHADOW if route == RouteTarget.SHADOW else CanaryMode.CANARY
    reason = (
        f"growthbook:{str(evaluation.value).lower()}"
        if evaluation.ready
        else "growthbook_unavailable_fail_closed"
    )
    return CanaryDecision(
        mode=mode,
        route=route,
        reason=reason,
        percent=0,
        allowlisted=False,
        key=normalized,
        source=evaluation.source,
        feature_key=evaluation.feature_key,
        flag_value=evaluation.value,
    )


def require_support_route(key: str) -> CanaryDecision:
    """Gate live support-agent workflow starts.

    - `force_legacy` → always reject (instant rollback)
    - `shadow` → reject live starts (use `/v2/shadow` only)
    - `canary` → allow only allowlist / percent bucket
    - `off` → allow (opt-in by calling this gateway; external router sends 0%)
    """
    decision = decide_route(key)
    force_legacy = os.getenv("SUPPORT_AGENT_FORCE_LEGACY", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if force_legacy:
        raise ValueError(
            f"route=legacy reason=force_legacy; "
            "use legacy gateway until SUPPORT_AGENT_FORCE_LEGACY is cleared"
        )
    if decision.mode == CanaryMode.SHADOW:
        raise ValueError(
            "route=shadow reason=shadow_mirror_only; "
            "live workflows disabled — use POST /v2/shadow"
        )
    if decision.mode == CanaryMode.CANARY and decision.route != RouteTarget.SUPPORT:
        raise ValueError(
            f"route={decision.route.value} reason={decision.reason}; "
            "not selected for canary — use legacy gateway or allowlist/percent"
        )
    if decision.mode == CanaryMode.OFF:
        return CanaryDecision(
            mode=decision.mode,
            route=RouteTarget.SUPPORT,
            reason="direct_gateway_opt_in",
            percent=decision.percent,
            allowlisted=decision.allowlisted,
            key=decision.key,
        )
    return decision


async def require_support_route_runtime(
    key: str,
    *,
    feature_flags: FeatureFlagProvider,
    attributes: dict[str, Any] | None = None,
) -> CanaryDecision:
    """Require the runtime flag decision to select the new support-agent."""
    if not feature_flags.status().get("enabled"):
        return require_support_route(key)
    decision = await decide_route_runtime(
        key,
        feature_flags=feature_flags,
        attributes=attributes,
    )
    if decision.route != RouteTarget.SUPPORT:
        raise ValueError(
            f"route={decision.route.value} reason={decision.reason}; "
            "GrowthBook did not select the new support-agent"
        )
    return decision


__all__ = [
    "CanaryDecision",
    "CanaryMode",
    "RouteTarget",
    "canary_config",
    "decide_route",
    "decide_route_runtime",
    "require_support_route",
    "require_support_route_runtime",
]
