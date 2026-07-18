"""Mail / Calendar port fakes + factory."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from am_platform_ports.fakes import FakeCalendar, FakeMail
from am_platform_ports.ports.calendar import CalendarPort
from am_platform_ports.ports.mail import MailPort


def test_fake_mail_and_calendar() -> None:
    mail: MailPort = FakeMail()
    cal: CalendarPort = FakeCalendar()
    mref = mail.send(to=["ops@example.com"], subject="s", body="b", refs={"run_ref": "r1"})
    assert mref.startswith("mail-")
    start = datetime.now(UTC)
    eref = cal.create_event(title="warroom", start=start, end=start + timedelta(hours=1))
    assert eref.startswith("event-")


def test_factory_mail_calendar_fake(monkeypatch) -> None:
    monkeypatch.setenv("MAIL_PROVIDER", "fake")
    monkeypatch.setenv("CALENDAR_PROVIDER", "fake")
    from am_platform_adapters import factory as af

    assert af.build_mail().__class__.__name__ == "FakeMail"
    assert af.build_calendar().__class__.__name__ == "FakeCalendar"


def test_resolve_access_token_prefers_refresh(monkeypatch) -> None:
    from am_platform_adapters.providers.zoho import oauth as zoho_oauth

    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "sec")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "ref")

    def _fake_refresh(**_kwargs):
        return "fresh-token"

    monkeypatch.setattr(zoho_oauth, "refresh_access_token", _fake_refresh)
    assert zoho_oauth.resolve_access_token(static_token="stale") == "fresh-token"


def test_resolve_access_token_falls_back_to_static(monkeypatch) -> None:
    from am_platform_adapters.providers.zoho import oauth as zoho_oauth

    for key in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    assert zoho_oauth.resolve_access_token(static_token="static-token") == "static-token"
