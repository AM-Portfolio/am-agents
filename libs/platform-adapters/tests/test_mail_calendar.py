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
