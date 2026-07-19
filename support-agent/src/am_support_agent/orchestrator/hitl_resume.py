"""Phase 2 HITL resume hooks (stubs).

Today `_handoff_to_human` terminates AlertIncidentWorkflow. Approvals for
investigation/known_fix cannot resume that run. Phase 2 should:

1. Start a child/follow-on workflow `AlertIncidentResumeWorkflow` on approval, OR
2. Keep the parent open in `awaiting_investigation_approval` / `awaiting_known_fix_approval`.

External close sync should emit `incident.hitl.resolved_external` into agent-ops
when alert_ops.issues or the ticket system closes the tracking_id.
"""

from __future__ import annotations

PHASE2_RESUME_PURPOSES = frozenset({"investigation", "known_fix"})
PHASE2_EXTERNAL_CLOSE_EVENT = "incident.hitl.resolved_external"


def resume_supported(purpose: str) -> bool:
    """Return False until Phase 2 resume workflow is wired."""
    del purpose
    return False
