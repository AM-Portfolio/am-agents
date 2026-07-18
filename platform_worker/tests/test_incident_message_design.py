"""Incident dual-channel message design tests."""

from __future__ import annotations

from am_platform_adapters.links import (
    grafana_tempo_trace_url,
    temporal_workflow_url,
    ticket_browser_url,
    ticket_number,
)
from am_platform_adapters.providers.cliq.notifier import _card_to_cliq_payload
from am_platform_ports.formatting.incident_email import (
    email_subject,
    render_incident_email_html,
    render_incident_email_text,
)
from am_platform_ports.formatting.incident_message import to_cliq_card, to_op_comment, to_ticket_comment
from am_platform_ports.schemas.incident_message import (
    DeveloperLinks,
    DeveloperNotes,
    IncidentMessage,
)
from platform_worker.notify_incident import (
    build_incident_message,
    comment_incident_phase,
    soft_ticket_comment,
)


def _resolved_msg() -> IncidentMessage:
    return IncidentMessage(
        tracking_id="AM-20260717-6AB6D2",
        alert_id="KubeServiceDown",
        ticket_ref="op:wp:386",
        ticket_number="386",
        status="RESOLVED",
        env="lab",
        severity="WARNING",
        problem="KubeServiceDown: redis in infra has 0 ready endpoints",
        reason="verify passed",
        success_summary="Prometheus endpoints ready; Redis alive via tool-agent",
        done_by="IT-Support-agent",
        responsible="Auth Test",
        backup="Gyaneshwar Kumar",
        team="platform",
        namespace="infra",
        app="redis",
        started_at="2026-07-17 20:45:00 UTC",
        notified_at="2026-07-17 21:02:43 UTC",
        ended_at="2026-07-17 21:02:00 UTC",
        decision="auto_infra",
        run_ref="run-abc",
        workflow_id="alert-incident-AM-20260717-6AB6D2",
        mail_teaser="Full report emailed to owner@example.com",
        links=DeveloperLinks(
            temporal_url="http://127.0.0.1:8080/namespaces/default/workflows/alert-incident-AM-20260717-6AB6D2",
            grafana_trace_url="",
            ticket_url="https://openproject.asrax.in/work_packages/386",
            ticket_label="OpenProject",
            alert_url="https://grafana.asrax.in/alerting/grafana/kube-service-down/view",
        ),
    )


def _failed_msg() -> IncidentMessage:
    m = _resolved_msg()
    m.status = "FAILED"
    m.reason = "verify failed: endpoints ready=0"
    m.success_summary = ""
    m.developer_notes = DeveloperNotes(
        developer_summary="Redis still reports not ready after auto remediation.",
        likely_owner="infra",
        gaps=["no trace_id on alert", "crashloop series unavailable"],
        next_steps=["Open Temporal run", "Inspect OP evidence JSON", "Check redis pods"],
        info_needed_to_close="Confirm rollout restart completed and endpoints > 0",
        move_to_development=False,
        move_to_development_why="Likely infra ops, not app code",
        source="template",
    )
    return m


def test_cliq_card_is_compact(monkeypatch) -> None:
    """Compact card with in-chat link buttons (no MinIO View more)."""
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.munish.org")
    card = to_cliq_card(_resolved_msg())
    assert "RESOLVED" in card.title
    assert "KubeServiceDown" in card.title or "WARNING" in card.title
    assert "Evidence dump" not in card.body
    assert len(card.body or "") <= 200
    rows = card.meta.get("table_rows") or []
    assert any(r.get("Field") == "Summary" for r in rows)
    assert any(r.get("Field") == "IDs" and "AM-20260717-6AB6D2" in r.get("Value", "") for r in rows)
    update = next((r.get("Value", "") for r in rows if r.get("Field") == "Update"), "")
    assert "cAdvisor" not in update
    assert len(update) <= 90
    buttons = card.meta.get("buttons") or []
    labels = [b.get("label") for b in buttons]
    assert "OpenProject" in labels
    assert "Open alert" in labels
    assert "Temporal" in labels
    assert "Langfuse" in labels
    assert "View more" not in labels
    assert "openproject.asrax.in" not in card.body
    payload = _card_to_cliq_payload(card)
    assert payload["slides"][0]["type"] == "table"
    assert all(b["action"]["type"] == "open.url" for b in payload["buttons"])


def test_cliq_timing_fields() -> None:
    msg = _resolved_msg()
    msg.started_at = "2026-07-17 20:45:00 UTC"
    msg.ended_at = "2026-07-17 21:02:00 UTC"
    rows = {r["Field"]: r["Value"] for r in (to_cliq_card(msg).meta.get("table_rows") or [])}
    assert rows.get("Received") == "2026-07-17 20:45:00 UTC"
    assert rows.get("Resolution") == "2026-07-17 21:02:00 UTC"
    assert rows.get("Time spent") == "17m 0s"
    assert "When" not in rows


def test_email_html_has_modern_sections() -> None:
    html = render_incident_email_html(_resolved_msg())
    assert "Developer Links" in html
    assert "Details" in html
    assert "RESOLVED" in html
    assert "openproject.asrax.in" in html
    assert "IT Support" in html
    assert email_subject(_resolved_msg()).startswith("[AM-20260717-6AB6D2] RESOLVED")


def test_failed_email_has_for_developers() -> None:
    html = render_incident_email_html(_failed_msg())
    assert "For developers" in html
    assert "Next steps" in html or "next" in html.lower()
    text = render_incident_email_text(_failed_msg())
    assert "For developers" in text
    card = to_cliq_card(_failed_msg())
    assert "Gaps" not in card.body
    rows = card.meta.get("table_rows") or []
    blob = " ".join(str(r.get("Value", "")) for r in rows)
    assert "crashloop" not in blob  # full notes stay in email/ticket


def test_op_comment_mid_detail() -> None:
    md = to_op_comment(_failed_msg())
    assert "Developer Links" in md
    assert "For developers" in md
    assert "386" in md or "op:wp:386" in md


def test_phase_ticket_comment_includes_checkpoint() -> None:
    body = to_ticket_comment(
        _failed_msg(),
        phase="VERIFY",
        extras=["verify_status=failed", "endpoints=0"],
    )
    assert "Phase: VERIFY" in body
    assert "Status: FAILED" in body
    assert "Developer Links" in body
    assert "Phase details" in body
    assert "endpoints=0" in body
    assert "earlier phases stay" in body.lower()


def test_jira_phase_comment_labels_provider() -> None:
    msg = _resolved_msg()
    msg.ticket_ref = "jira:LAB-42"
    msg.ticket_number = "LAB-42"
    body = to_ticket_comment(msg, phase="DECISION")
    assert "Provider: Jira" in body
    assert "Phase: DECISION" in body


def test_soft_ticket_comment_survives_failure() -> None:
    class BoomTickets:
        def comment(self, *, ticket_ref: str, body: str) -> None:
            raise RuntimeError("jira down")

    class Ports:
        tickets = BoomTickets()

    assert soft_ticket_comment(Ports(), ticket_ref="jira:X-1", body="hi").startswith("error:")
    msg = _resolved_msg()
    msg.ticket_ref = "jira:X-1"
    assert comment_incident_phase(Ports(), msg=msg, phase="INTAKE").startswith("error:")


def test_phase_comments_accumulate_on_fake_ticket() -> None:
    from am_platform_ports.fakes import FakeTicketStore

    store = FakeTicketStore()
    ticket = store.create(title="t", description="d", priority="P3")
    msg = _resolved_msg()
    msg.ticket_ref = ticket.ticket_ref

    class Ports:
        tickets = store

    assert comment_incident_phase(Ports(), msg=msg, phase="INTAKE") == "ok"
    msg.status = "AUTO_INFRA"
    assert comment_incident_phase(Ports(), msg=msg, phase="DECISION") == "ok"
    msg.status = "FAILED"
    assert comment_incident_phase(Ports(), msg=msg, phase="VERIFY", extras=["failed"]) == "ok"
    comments = store.tickets[ticket.ticket_ref]["comments"]
    assert len(comments) == 3
    assert "Phase: INTAKE" in comments[0]
    assert "Phase: DECISION" in comments[1]
    assert "Phase: VERIFY" in comments[2]
    # Prior phases remain even after later failure comment
    assert "Phase: INTAKE" in comments[0]


def test_link_helpers(monkeypatch) -> None:
    from am_platform_adapters.links import (
        grafana_alert_url,
        langfuse_trace_url,
        normalize_grafana_url,
    )

    monkeypatch.setenv("OPENPROJECT_PUBLIC_URL", "https://openproject.asrax.in")
    monkeypatch.setenv("GRAFANA_EXTERNAL_URL", "https://grafana.asrax.in")
    monkeypatch.setenv("TEMPORAL_UI_EXTERNAL_URL", "https://temporal.asrax.in")
    monkeypatch.setenv("LANGFUSE_PUBLIC_URL", "https://langfuse.munish.org")
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", "cmsupportagent0001wx0dsa001")
    monkeypatch.setenv(
        "LINK_ALLOWED_HOSTS",
        "grafana.munish.org,grafana.asrax.in,openproject.asrax.in,temporal.asrax.in,langfuse.munish.org,127.0.0.1",
    )
    assert ticket_number("op:wp:386") == "386"
    assert "386" in ticket_browser_url("op:wp:386")
    assert "explore" in grafana_tempo_trace_url("abc123")
    assert "workflows" in temporal_workflow_url("wf-1", env="lab")
    hist = temporal_workflow_url(
        "alert-incident-AM-20260718-5511ED",
        run_id="019f7773-7e1c-7994-9df4-190dc6445b0a",
        env="lab",
    )
    assert hist.endswith(
        "/workflows/alert-incident-AM-20260718-5511ED/"
        "019f7773-7e1c-7994-9df4-190dc6445b0a/history"
    )
    assert "/alerting/list" not in grafana_alert_url(
        "https://grafana./alerting/list?search=DatasourceError",
        alertname="DatasourceError",
    )
    assert "alerting/groups" in grafana_alert_url(
        "https://grafana./alerting/list?search=DatasourceError",
        alertname="DatasourceError",
    )
    assert normalize_grafana_url(
        "https://grafana./alerting/grafana/abc/view"
    ).startswith("https://grafana.asrax.in/")
    lf = langfuse_trace_url("731e0f90-8972-4d64-a3b3-45874709042b")
    assert lf == (
        "https://langfuse.munish.org/project/cmsupportagent0001wx0dsa001/"
        "traces/731e0f90-8972-4d64-a3b3-45874709042b"
    )
    assert "project/cmsupportagent0001wx0dsa001/traces?search=" in langfuse_trace_url(
        tracking_id="AM-20260718-5511ED"
    )


def test_build_incident_message_resolved() -> None:
    msg = build_incident_message(
        status="RESOLVED",
        tracking_id="AM-REAL-1",
        alert={
            "summary": "redis down",
            "generator_url": "https://grafana.asrax.in/alerting/x",
            "labels": {"alertname": "KubeServiceDown", "env": "lab", "namespace": "infra"},
        },
        ticket_ref="op:wp:1",
        env="lab",
        reason="ok",
        success_summary="endpoints ready",
        workflow_id="alert-incident-AM-REAL-1",
        assignee_email="dev@example.com",
        ended=True,
    )
    assert msg.status == "RESOLVED"
    assert msg.links.ticket_url
    assert "emailed" in msg.mail_teaser.lower() or "Mail skipped" in msg.mail_teaser
