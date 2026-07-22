from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

from app.config import settings

# Wide pad so sparse post-run points still land in the visible window.
_PAD_BEFORE_MIN = 30
_PAD_AFTER_MIN = 30


def _ms(iso: str | None) -> int:
    if not iso:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except ValueError:
        return int(datetime.now(timezone.utc).timestamp() * 1000)


def grafana_run_url(
    *,
    service: str | None = None,
    environment: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    run_id: str | None = None,
) -> str:
    """Deep-link the SPT dashboard locked to one run (no manual Grafana filters)."""
    base = settings.grafana_public_url.rstrip("/")
    uid = settings.grafana_k6_dashboard_uid
    from_ms = _ms(started_at) - _PAD_BEFORE_MIN * 60_000
    to_ms = _ms(finished_at or started_at) + _PAD_AFTER_MIN * 60_000
    if to_ms <= from_ms:
        to_ms = from_ms + 60 * 60_000

    params: dict[str, str] = {
        "orgId": "1",
        "from": str(from_ms),
        "to": str(to_ms),
        # Always set filters so Grafana never prompts "configure".
        "var-service": service or "All",
        "var-environment": environment or "All",
        "var-run_id": run_id or "All",
        "var-api_id": "All",
    }
    return f"{base}/d/{uid}/spt-load-testing?{urlencode(params)}"


def grafana_embed_url(**kwargs) -> str:
    url = grafana_run_url(**kwargs)
    return url + "&kiosk=tv"
