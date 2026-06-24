from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_RELATIVE_RE = re.compile(r"^now(-(\d+)([mhd]))?$", re.I)


def grafana_time_to_rfc3339(value: str) -> str:
    text = value.strip()
    if not text.lower().startswith("now"):
        return text
    if text.lower() == "now":
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    match = _RELATIVE_RE.match(text)
    if not match:
        return text
    amount = int(match.group(2))
    unit = match.group(3).lower()
    if unit == "m":
        delta = timedelta(minutes=amount)
    elif unit == "h":
        delta = timedelta(hours=amount)
    else:
        delta = timedelta(days=amount)
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")
