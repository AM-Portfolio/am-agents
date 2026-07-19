"""Legacy parity and shadow comparison."""

from am_support_agent.parity.canary import (
    CanaryDecision,
    CanaryMode,
    RouteTarget,
    canary_config,
    decide_route,
    decide_route_runtime,
    require_support_route,
    require_support_route_runtime,
)
from am_support_agent.parity.growthbook_flags import (
    FeatureFlagEvaluation,
    FeatureFlagProvider,
    GrowthBookFeatureFlags,
    build_feature_flags,
)
from am_support_agent.parity.comparator import (
    DEFAULT_IGNORED_KEYS,
    SHADOW_MATCH_THRESHOLD,
    SOFT_MATCH_THRESHOLD,
    ParityDifference,
    ParityReport,
    compare_results,
    meets_parity_threshold,
)

__all__ = [
    "CanaryDecision",
    "CanaryMode",
    "DEFAULT_IGNORED_KEYS",
    "FeatureFlagEvaluation",
    "FeatureFlagProvider",
    "GrowthBookFeatureFlags",
    "RouteTarget",
    "SHADOW_MATCH_THRESHOLD",
    "SOFT_MATCH_THRESHOLD",
    "ParityDifference",
    "ParityReport",
    "canary_config",
    "build_feature_flags",
    "compare_results",
    "decide_route",
    "decide_route_runtime",
    "meets_parity_threshold",
    "require_support_route",
    "require_support_route_runtime",
]
