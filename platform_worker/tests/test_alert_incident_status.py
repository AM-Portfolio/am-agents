"""AlertIncidentWorkflow status exposes verify evidence/reason."""

from __future__ import annotations

from platform_worker.workflows.alert_incident import AlertIncidentWorkflow


def test_workflow_status_exposes_verify_evidence_and_reason() -> None:
    wf = AlertIncidentWorkflow()
    wf._run_ref = "run-1"
    wf._ticket_ref = "ticket-1"
    wf._verify_run_ref = "verify-1"
    wf._verify_status = "failed"
    wf._verify_reason = (
        "verify failed: verify.k8s.endpoints.ready=FAIL: Prometheus value=0; "
        "verify.service.alive=FAIL: tool-agent unreachable"
    )
    wf._verify_evidence = [
        {
            "check_ref": "verify.k8s.endpoints.ready",
            "query_ref": "k8s.endpoints.ready",
            "passed": False,
            "status": "failed",
            "source": "prometheus",
            "reason": "Prometheus k8s.endpoints.ready failed: value=0.0 does not satisfy value > 0",
            "value": 0.0,
            "pass_when": "value > 0",
            "error": None,
            "result_ref": "docs://verify/1.json",
        },
        {
            "check_ref": "verify.service.alive",
            "query_ref": "redis.service.alive",
            "passed": False,
            "status": "failed",
            "source": "tool-agent:redis.info",
            "reason": "Redis service-alive check failed: tool-agent unreachable",
            "value": None,
            "error": "tool-agent unreachable",
            "result_ref": None,
        },
    ]
    wf._decision = "auto_infra"

    status = wf.status()
    assert status["verify_status"] == "failed"
    assert status["verify_reason"]
    assert "FAIL" in status["verify_reason"] or "failed" in status["verify_reason"]
    assert len(status["verify_evidence"]) == 2
    assert status["verify_evidence"][0]["source"] == "prometheus"
    assert status["verify_evidence"][1]["source"] == "tool-agent:redis.info"
    assert all(e.get("reason") for e in status["verify_evidence"])


def test_workflow_status_success_evidence() -> None:
    wf = AlertIncidentWorkflow()
    wf._verify_status = "passed"
    wf._verify_reason = "verify passed: verify.k8s.endpoints.ready=PASS: ok"
    wf._verify_evidence = [
        {
            "check_ref": "verify.k8s.endpoints.ready",
            "query_ref": "k8s.endpoints.ready",
            "passed": True,
            "status": "passed",
            "source": "prometheus",
            "reason": "Prometheus k8s.endpoints.ready passed: value=1.0 satisfies value > 0",
            "value": 1.0,
        }
    ]
    status = wf.status()
    assert status["verify_status"] == "passed"
    assert status["verify_evidence"][0]["passed"] is True
    assert "passed" in status["verify_reason"]
