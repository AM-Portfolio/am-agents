"""Canary routing and rollback tests."""

from __future__ import annotations

import pytest

from am_support_agent.parity.canary import (
    CanaryMode,
    RouteTarget,
    decide_route,
    decide_route_runtime,
    require_support_route,
    require_support_route_runtime,
)
from am_support_agent.parity.growthbook_flags import (
    FeatureFlagEvaluation,
    GrowthBookFeatureFlags,
)


class FakeFeatureFlags:
    def __init__(self, value, *, ready=True):
        self.value = value
        self.ready = ready

    def status(self):
        return {"enabled": True, "ready": self.ready}

    async def evaluate(self, feature_key, *, fallback, attributes):
        return FeatureFlagEvaluation(
            feature_key=feature_key,
            value=self.value if self.ready else fallback,
            source="growthbook",
            ready=self.ready,
            error="" if self.ready else "unavailable",
        )

    async def close(self):
        return None


def test_canary_off_defaults_to_legacy_for_splitter(monkeypatch):
    monkeypatch.delenv("SUPPORT_AGENT_FORCE_LEGACY", raising=False)
    monkeypatch.setenv("SUPPORT_AGENT_CANARY_MODE", "off")
    d = decide_route("trk-1")
    assert d.route == RouteTarget.LEGACY
    # Direct gateway opt-in still allowed
    allowed = require_support_route("trk-1")
    assert allowed.route == RouteTarget.SUPPORT
    assert allowed.reason == "direct_gateway_opt_in"


def test_force_legacy_rollback(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_FORCE_LEGACY", "true")
    monkeypatch.setenv("SUPPORT_AGENT_CANARY_MODE", "canary")
    monkeypatch.setenv("SUPPORT_AGENT_CANARY_PERCENT", "100")
    d = decide_route("trk-1")
    assert d.route == RouteTarget.LEGACY
    assert d.reason == "force_legacy"
    with pytest.raises(ValueError, match="force_legacy"):
        require_support_route("trk-1")


def test_shadow_blocks_live_workflows(monkeypatch):
    monkeypatch.delenv("SUPPORT_AGENT_FORCE_LEGACY", raising=False)
    monkeypatch.setenv("SUPPORT_AGENT_CANARY_MODE", "shadow")
    d = decide_route("trk-1")
    assert d.route == RouteTarget.SHADOW
    with pytest.raises(ValueError, match="shadow"):
        require_support_route("trk-1")


def test_canary_allowlist(monkeypatch):
    monkeypatch.delenv("SUPPORT_AGENT_FORCE_LEGACY", raising=False)
    monkeypatch.setenv("SUPPORT_AGENT_CANARY_MODE", "canary")
    monkeypatch.setenv("SUPPORT_AGENT_CANARY_PERCENT", "0")
    monkeypatch.setenv("SUPPORT_AGENT_CANARY_ALLOWLIST", "trk-allow,other")
    assert decide_route("trk-allow").route == RouteTarget.SUPPORT
    assert decide_route("trk-deny").route == RouteTarget.LEGACY
    require_support_route("trk-allow")
    with pytest.raises(ValueError):
        require_support_route("trk-deny")


def test_canary_percent_sticky(monkeypatch):
    monkeypatch.delenv("SUPPORT_AGENT_FORCE_LEGACY", raising=False)
    monkeypatch.setenv("SUPPORT_AGENT_CANARY_MODE", "canary")
    monkeypatch.setenv("SUPPORT_AGENT_CANARY_PERCENT", "100")
    monkeypatch.delenv("SUPPORT_AGENT_CANARY_ALLOWLIST", raising=False)
    d = decide_route("any-key")
    assert d.mode == CanaryMode.CANARY
    assert d.route == RouteTarget.SUPPORT


@pytest.mark.asyncio
async def test_growthbook_selects_new_support_agent(monkeypatch):
    monkeypatch.delenv("SUPPORT_AGENT_FORCE_LEGACY", raising=False)
    monkeypatch.setenv("GROWTHBOOK_ROUTE_FEATURE_KEY", "support-agent-route")
    flags = FakeFeatureFlags("new")
    decision = await decide_route_runtime("trk-new", feature_flags=flags)
    assert decision.route == RouteTarget.SUPPORT
    assert decision.source == "growthbook"
    assert decision.feature_key == "support-agent-route"
    await require_support_route_runtime("trk-new", feature_flags=flags)


@pytest.mark.asyncio
async def test_growthbook_selects_legacy(monkeypatch):
    monkeypatch.delenv("SUPPORT_AGENT_FORCE_LEGACY", raising=False)
    flags = FakeFeatureFlags("legacy")
    decision = await decide_route_runtime("trk-old", feature_flags=flags)
    assert decision.route == RouteTarget.LEGACY
    with pytest.raises(ValueError, match="GrowthBook"):
        await require_support_route_runtime("trk-old", feature_flags=flags)


@pytest.mark.asyncio
async def test_growthbook_failure_fails_closed_to_legacy(monkeypatch):
    monkeypatch.delenv("SUPPORT_AGENT_FORCE_LEGACY", raising=False)
    decision = await decide_route_runtime(
        "trk-fail",
        feature_flags=FakeFeatureFlags("new", ready=False),
    )
    assert decision.route == RouteTarget.LEGACY
    assert decision.reason == "growthbook_unavailable_fail_closed"


@pytest.mark.asyncio
async def test_growthbook_missing_client_key_fails_closed():
    flags = GrowthBookFeatureFlags(enabled=True, client_key="")
    evaluation = await flags.evaluate(
        "support-agent-route",
        fallback="legacy",
        attributes={"id": "trk-1"},
    )
    assert evaluation.value == "legacy"
    assert evaluation.ready is False
    assert "GROWTHBOOK_CLIENT_KEY" in evaluation.error
