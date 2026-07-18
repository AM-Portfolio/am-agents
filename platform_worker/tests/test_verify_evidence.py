"""Verify activity evidence serialization (pass + fail)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from am_platform_ports.fakes import FakeDocStore, FakeRunStore
from am_platform_ports.schemas.enums import RunKind, RunStatus, StepStatus
from am_platform_ports.schemas.run import CreateRunRequest, UpsertStepRequest
from platform_worker.activities import verify as verify_mod
from platform_worker.di import Ports, reset_ports_for_tests


@dataclass
class _FakeObserve:
    results: dict[str, dict[str, Any]]

    def query(self, *, query_ref: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        return dict(self.results.get(query_ref) or {"pass": False, "error": "missing", "query_ref": query_ref})


def _install_ports(observe: Any) -> Ports:
    reset_ports_for_tests()
    runs = FakeRunStore()
    ports = Ports(
        triage=MagicMock(),
        directory=MagicMock(),
        tickets=MagicMock(),
        notifier=MagicMock(),
        prompts=MagicMock(),
        runs=runs,
        docs=FakeDocStore(),
        observe=observe,
        infra=MagicMock(),
        redactor=MagicMock(),
        llm=MagicMock(),
        mail=MagicMock(),
        handoff=MagicMock(),
        spt_catalog=MagicMock(),
        spt_resolver=MagicMock(),
        spt_policy=MagicMock(),
        spt_prep=MagicMock(),
        spt_runner=MagicMock(),
    )
    verify_mod.get_ports = lambda: ports  # type: ignore[attr-defined]
    return ports


@pytest.fixture(autouse=True)
def _restore_get_ports():
    original = verify_mod.get_ports
    yield
    verify_mod.get_ports = original  # type: ignore[attr-defined]
    reset_ports_for_tests()


@pytest.fixture
def catalog_path(tmp_path, monkeypatch):
    path = tmp_path / "checks.yaml"
    path.write_text(
        """
checks:
  - check_ref: verify.k8s.endpoints.ready
    kind: metrics
    query_ref: k8s.endpoints.ready
    pass_when: "value > 0"
  - check_ref: verify.service.alive
    kind: metrics
    query_ref: redis.service.alive
    pass_when: "value == 1"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("VERIFY_CATALOG_PATH", str(path))
    # Ensure no VERIFY_FORCE on live path
    monkeypatch.delenv("VERIFY_FORCE_RESULT", raising=False)
    return path


def _seed_verify_run(ports: Ports) -> str:
    parent = ports.runs.create_run(
        CreateRunRequest(kind=RunKind.ALERT_INCIDENT, status=RunStatus.RUNNING)
    )
    verify = ports.runs.create_run(
        CreateRunRequest(
            kind=RunKind.VERIFY,
            status=RunStatus.ACCEPTED,
            parent_run_ref=parent.run_ref,
        )
    )
    for check_ref in ("verify.k8s.endpoints.ready", "verify.service.alive"):
        ports.runs.upsert_step(
            UpsertStepRequest(
                step_ref=f"{verify.run_ref}:{check_ref}",
                run_ref=verify.run_ref,
                name=check_ref,
                check_ref=check_ref,
                status=StepStatus.PENDING,
            )
        )
    return verify.run_ref


@pytest.mark.asyncio
async def test_claim_and_execute_verify_evidence_pass(catalog_path) -> None:
    observe = _FakeObserve(
        {
            "k8s.endpoints.ready": {
                "pass": True,
                "source": "prometheus",
                "value": 1.0,
                "pass_when": "value > 0",
                "reason": "Prometheus k8s.endpoints.ready passed: value=1.0 satisfies value > 0",
                "query_ref": "k8s.endpoints.ready",
            },
            "redis.service.alive": {
                "pass": True,
                "source": "tool-agent:redis.info",
                "value": 1.0,
                "pass_when": "value == 1",
                "reason": "Redis reachable via tool-agent redis.info (redis_version=7.2.0)",
                "request_id": "req-abc",
                "redis_version": "7.2.0",
                "uptime_in_seconds": 42,
                "query_ref": "redis.service.alive",
            },
        }
    )
    ports = _install_ports(observe)
    verify_run_ref = _seed_verify_run(ports)

    out = await verify_mod.claim_and_execute_verify(
        {
            "verify_run_ref": verify_run_ref,
            "incident_ref": "AM-1",
            "env": "lab",
            "alert": {"labels": {"service": "redis", "namespace": "infra"}},
            "worker_id": "test-worker",
        }
    )
    assert out["status"] == "passed"
    assert out["passed"] == 2
    assert out["failed"] == 0
    assert "verify_reason" in out
    assert "PASS" in out["verify_reason"]
    evidence = out["evidence"]
    assert len(evidence) == 2
    by_ref = {e["check_ref"]: e for e in evidence}
    assert by_ref["verify.k8s.endpoints.ready"]["passed"] is True
    assert by_ref["verify.k8s.endpoints.ready"]["source"] == "prometheus"
    assert "reason" in by_ref["verify.k8s.endpoints.ready"]
    assert by_ref["verify.service.alive"]["source"] == "tool-agent:redis.info"
    assert by_ref["verify.service.alive"]["request_id"] == "req-abc"
    assert by_ref["verify.service.alive"]["metadata"]["redis_version"] == "7.2.0"
    assert by_ref["verify.service.alive"]["result_ref"]
    assert os.getenv("VERIFY_FORCE_RESULT", "") == ""


@pytest.mark.asyncio
async def test_claim_and_execute_verify_evidence_fail(catalog_path) -> None:
    observe = _FakeObserve(
        {
            "k8s.endpoints.ready": {
                "pass": False,
                "source": "prometheus",
                "value": 0.0,
                "pass_when": "value > 0",
                "reason": "Prometheus k8s.endpoints.ready failed: value=0.0 does not satisfy value > 0",
                "query_ref": "k8s.endpoints.ready",
            },
            "redis.service.alive": {
                "pass": False,
                "source": "tool-agent:redis.info",
                "error": "tool-agent unreachable: boom",
                "reason": "Redis service-alive check failed: tool-agent unreachable: boom",
                "query_ref": "redis.service.alive",
            },
        }
    )
    ports = _install_ports(observe)
    verify_run_ref = _seed_verify_run(ports)

    out = await verify_mod.claim_and_execute_verify(
        {
            "verify_run_ref": verify_run_ref,
            "incident_ref": "AM-2",
            "env": "lab",
            "alert": {"labels": {"service": "redis", "namespace": "infra"}},
            "worker_id": "test-worker",
        }
    )
    assert out["status"] == "failed"
    assert out["failed"] == 2
    evidence = out["verify_evidence"]
    assert all(e["passed"] is False for e in evidence)
    assert all(e.get("reason") for e in evidence)
    assert "FAIL" in out["verify_reason"]
    # Failure reasons visible for prometheus zero and tool-agent error
    reasons = " ".join(e["reason"] for e in evidence)
    assert "0.0" in reasons or "does not satisfy" in reasons
    assert "unreachable" in reasons or "boom" in reasons


@pytest.mark.asyncio
async def test_no_verify_force_on_live_path(catalog_path, monkeypatch) -> None:
    """Even if VERIFY_FORCE is set in env, activity uses observe port result (not force)."""
    monkeypatch.setenv("VERIFY_FORCE_RESULT", "passed")
    observe = _FakeObserve(
        {
            "k8s.endpoints.ready": {
                "pass": False,
                "source": "prometheus",
                "value": 0.0,
                "reason": "prometheus zero",
                "query_ref": "k8s.endpoints.ready",
            },
            "redis.service.alive": {
                "pass": False,
                "source": "tool-agent:redis.info",
                "error": "err",
                "reason": "tool-agent error",
                "query_ref": "redis.service.alive",
            },
        }
    )
    ports = _install_ports(observe)
    verify_run_ref = _seed_verify_run(ports)
    out = await verify_mod.claim_and_execute_verify(
        {
            "verify_run_ref": verify_run_ref,
            "incident_ref": "AM-3",
            "env": "lab",
            "alert": {"labels": {"service": "redis"}},
            "worker_id": "test-worker",
        }
    )
    # Force env must not flip observe results in this activity
    assert out["status"] == "failed"
    assert all(e["passed"] is False for e in out["evidence"])
