"""Jira TicketStore unit tests (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock

from am_platform_adapters.providers.jira.client import JiraClient
from am_platform_adapters.providers.jira.ticket_store import JiraTicketStore, _issue_key


def test_issue_key() -> None:
    assert _issue_key("jira:OPS-12") == "OPS-12"
    assert _issue_key("OPS-99") == "OPS-99"


def test_jira_create_assign_comment(monkeypatch) -> None:
    client = MagicMock(spec=JiraClient)
    client.post.side_effect = [
        {"key": "OPS-42", "id": "10001"},
        {},  # comment
        {},  # transition
    ]
    client.get.return_value = {
        "transitions": [{"id": "31", "name": "Done"}, {"id": "21", "name": "In Progress"}]
    }
    client.put.return_value = {}
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")

    store = JiraTicketStore(client=client, project_key="OPS", issue_type="Task")
    ref = store.create(title="alert", description="body", priority="P1", labels={"team": "lab"})
    assert ref.ticket_ref == "jira:OPS-42"
    assert ref.url and "OPS-42" in ref.url

    store.assign(ticket_ref=ref.ticket_ref, assignee_ref="jira:user:abc")
    assert client.put.call_args[0][0].endswith("/assignee")

    store.comment(ticket_ref=ref.ticket_ref, body="hi")
    store.update_status(ticket_ref=ref.ticket_ref, status="done")
    assert "transitions" in client.post.call_args[0][0]


def test_factory_jira(monkeypatch) -> None:
    monkeypatch.setenv("TICKET_PROVIDER", "jira")
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "a@b.c")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "OPS")
    from am_platform_adapters import factory as af

    assert af.build_ticket_store().__class__.__name__ == "JiraTicketStore"
