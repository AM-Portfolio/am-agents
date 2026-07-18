"""Worker safety tests (no Temporal cluster required)."""

from __future__ import annotations

import pytest


def test_refuse_legacy_queue_helper():
    from am_support_agent.orchestrator.worker_main import assert_safe_task_queue

    assert_safe_task_queue("support-agent-v2")
    with pytest.raises(SystemExit):
        assert_safe_task_queue("agent-platform")
