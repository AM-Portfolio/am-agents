"""OpenProject TicketStore / Directory unit tests (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock

from am_platform_adapters.providers.openproject.client import OpenProjectClient
from am_platform_adapters.providers.openproject.directory import OpenProjectDirectory
from am_platform_adapters.providers.openproject.ticket_store import (
    OpenProjectTicketStore,
    _assignee_href,
    _wp_id,
)


def test_wp_id_and_assignee_href() -> None:
    assert _wp_id("op:wp:42") == 42
    assert _wp_id("99") == 99
    assert _assignee_href("op:user:4") == "/api/v3/users/4"
    assert _assignee_href("7") == "/api/v3/users/7"


def test_directory_uses_existing_project_member() -> None:
    client = MagicMock(spec=OpenProjectClient)
    client.get.side_effect = [
        # memberships
        {
            "_embedded": {
                "elements": [
                    {
                        "_links": {
                            "principal": {
                                "href": "/api/v3/users/5",
                                "title": "munish munish",
                            }
                        }
                    },
                    {
                        "_links": {
                            "principal": {
                                "href": "/api/v3/users/6",
                                "title": "Sagar Asrax",
                            }
                        }
                    },
                ]
            }
        },
        # user 5
        {"id": 5, "login": "munish"},
        # user 6
        {"id": 6, "login": "sagar"},
    ]
    d = OpenProjectDirectory(
        client=client,
        project_id=3,
        default_assignee_login="munish",
        assignee_map={"platform": "sagar"},
        channel_ref="cliq:lab",
    )
    hit = d.resolve(labels={"team": "platform"}, priority="P1")
    assert hit.assignee_ref == "op:user:6"
    hit2 = d.resolve(labels={"assignee": "munish"}, priority="P2")
    assert hit2.assignee_ref == "op:user:5"


def test_ticket_create_assign_status(monkeypatch) -> None:
    client = MagicMock(spec=OpenProjectClient)
    client.post.return_value = {"id": 101, "lockVersion": 0}
    client.get.return_value = {"id": 101, "lockVersion": 1}
    client.patch.return_value = {"id": 101, "lockVersion": 2}

    store = OpenProjectTicketStore(client=client, project_id=3, type_id=1)
    monkeypatch.setenv("OPENPROJECT_PUBLIC_URL", "https://openproject.asrax.in")

    ref = store.create(title="[P1] smoke", description="body", priority="P1", labels={"team": "lab"})
    assert ref.ticket_ref == "op:wp:101"
    assert ref.url == "https://openproject.asrax.in/work_packages/101"
    assert client.post.call_args[0][0] == "/api/v3/work_packages"
    body = client.post.call_args[0][1]
    assert body["_links"]["project"]["href"] == "/api/v3/projects/3"
    assert body["_links"]["type"]["href"] == "/api/v3/types/1"

    store.assign(ticket_ref=ref.ticket_ref, assignee_ref="op:user:5")
    patch_body = client.patch.call_args[0][1]
    assert patch_body["_links"]["assignee"]["href"] == "/api/v3/users/5"

    store.update_status(ticket_ref=ref.ticket_ref, status="in_progress")
    status_body = client.patch.call_args[0][1]
    assert status_body["_links"]["status"]["href"] == "/api/v3/statuses/7"

    store.comment(ticket_ref=ref.ticket_ref, body="hello")
    assert client.post.call_args[0][0] == "/api/v3/work_packages/101/activities"


def test_factory_openproject(monkeypatch) -> None:
    monkeypatch.setenv("TICKET_PROVIDER", "openproject")
    monkeypatch.setenv("DIRECTORY_PROVIDER", "openproject")
    monkeypatch.setenv("OPENPROJECT_URL", "https://openproject.asrax.in")
    monkeypatch.setenv("OPENPROJECT_API_TOKEN", "tok")
    monkeypatch.setenv("OPENPROJECT_PROJECT_ID", "3")

    from am_platform_adapters import factory as af

    tickets = af.build_ticket_store()
    directory = af.build_directory()
    assert tickets.__class__.__name__ == "OpenProjectTicketStore"
    assert directory.__class__.__name__ == "OpenProjectDirectory"
