"""Dispatch outbox events to agent-ops-runtime (or log sink)."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from am_support_agent.stores.telemetry_outbox import build_telemetry_outbox

LOG = logging.getLogger("support_agent.telemetry.dispatcher")


def _post_batch(url: str, token: str, events: list[dict]) -> None:
    body = json.dumps({"events": events}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}" if token else "",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — cluster URL
        if resp.status not in {200, 202}:
            raise RuntimeError(f"agent-ops status {resp.status}")


def dispatch_once(*, batch_size: int = 50) -> int:
    outbox = build_telemetry_outbox()
    url = (os.getenv("AGENT_OPS_INGEST_URL") or "").strip()
    token = (os.getenv("AGENT_OPS_INGEST_TOKEN") or "").strip()
    claimed = outbox.claim_batch(limit=batch_size, locker="support-dispatcher")
    if not claimed:
        return 0
    if not url:
        # Dev fallback: treat as delivered after structured log.
        for rec in claimed:
            LOG.info(
                "agent_work_event %s",
                json.dumps(
                    {
                        "event_name": rec.event_name,
                        "tracking_id": rec.event.get("tracking_id"),
                        "status": rec.event.get("status"),
                        "outcome": rec.event.get("outcome"),
                        "event_id": rec.event_id,
                    }
                ),
            )
            outbox.mark_delivered(rec.event_id)
        return len(claimed)

    try:
        _post_batch(url, token, [r.event for r in claimed])
        for rec in claimed:
            outbox.mark_delivered(rec.event_id)
        return len(claimed)
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        for rec in claimed:
            outbox.mark_failed(rec.event_id, str(exc))
        LOG.warning("dispatch failed: %s", exc)
        return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    interval = float(os.getenv("AGENT_OPS_DISPATCH_INTERVAL_SECONDS") or "5")
    LOG.info("telemetry dispatcher starting interval=%s", interval)
    while True:
        try:
            n = dispatch_once()
            if n:
                LOG.info("dispatched %s events", n)
        except Exception as exc:  # noqa: BLE001
            LOG.exception("dispatcher loop error: %s", exc)
        time.sleep(interval)


if __name__ == "__main__":
    main()
