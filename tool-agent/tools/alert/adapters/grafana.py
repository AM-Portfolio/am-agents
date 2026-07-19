"""Grafana Alertmanager silence adapter — wraps am-obs-platform client when available."""

from __future__ import annotations

import os
from typing import Any


class Adapter:
    @property
    def available(self) -> bool:
        return bool(
            os.getenv("GRAFANA_API_URL")
            or os.getenv("GRAFANA_EXTERNAL_URL")
        )

    def _client(self):
        try:
            from providers.grafana.silence.grafana_http import GrafanaHttpSilenceClient
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Grafana silence adapter unavailable; install am-obs-platform providers "
                "or use ALERT_SILENCE_PROVIDER=memory"
            ) from exc
        return GrafanaHttpSilenceClient(
            api_url=(
                os.getenv("GRAFANA_API_URL")
                or os.getenv("GRAFANA_EXTERNAL_URL")
            ),
            user=os.getenv("GRAFANA_API_USER"),
            password=os.getenv("GRAFANA_API_PASSWORD")
            or os.getenv("GRAFANA_SERVICE_ACCOUNT_TOKEN"),
        )

    async def execute(self, operation: str, params: dict[str, Any], *, read_only: bool) -> dict[str, Any]:
        _ = read_only
        client = self._client()
        if operation == "silence.create":
            result = client.create(
                env=str(params.get("env") or ""),
                service=str(params.get("service") or ""),
                minutes=int(params.get("minutes") or 60),
                reason=str(params.get("reason") or ""),
                created_by=str(params.get("created_by") or "support-agent"),
            )
            return {
                "silence_id": result.silence_id,
                "starts_at": result.starts_at.isoformat().replace("+00:00", "Z"),
                "ends_at": result.ends_at.isoformat().replace("+00:00", "Z"),
            }
        if operation == "silence.get":
            silence_id = str(params.get("silence_id") or "")
            for silence in client.list_active():
                sid = getattr(silence, "id", None) or (
                    silence.get("id") if isinstance(silence, dict) else None
                )
                if sid == silence_id:
                    if isinstance(silence, dict):
                        return silence
                    return {"silence_id": sid, "found": True}
            return {"silence_id": silence_id, "found": False}
        if operation == "silence.expire":
            client.expire(
                str(params.get("silence_id") or ""),
                expired_by=str(params.get("expired_by") or "support-agent"),
            )
            return {"silence_id": params.get("silence_id"), "expired": True}
        raise ValueError(f"unknown operation {operation!r}")
