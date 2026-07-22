from __future__ import annotations

from typing import Any, Callable

import httpx

from app.config import settings
from app.config_builder import snapshot_for_run
from app.load_runner import run_k6_local

ProgressCb = Callable[[dict[str, Any]], None]


async def platform_health() -> dict[str, Any]:
    out: dict[str, Any] = {
        "k6_binary": __import__("pathlib").Path(settings.k6_bin).is_file(),
        "influxdb": {"configured": bool(settings.influxdb_token), "url": settings.influxdb_url},
        "minio": {"configured": bool(settings.minio_access_key), "bucket": settings.minio_bucket},
        "grafana_url": settings.grafana_public_url,
        "testkube": {"enabled": settings.testkube_enabled, "url": settings.testkube_api_url},
    }
    if settings.testkube_enabled:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{settings.testkube_api_url.rstrip('/')}/info")
                out["testkube"]["reachable"] = r.status_code < 400
        except Exception as exc:
            out["testkube"]["reachable"] = False
            out["testkube"]["error"] = str(exc)
    return out


async def run_test_from_config(
    config: dict[str, Any],
    *,
    triggered_by: str = "manual",
    run_id: str | None = None,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    if settings.testkube_enabled:
        try:
            rec = await _run_via_testkube(config, triggered_by=triggered_by)
            if rec:
                return rec
        except Exception:
            pass
    record = await run_k6_local(
        config,
        triggered_by=triggered_by,
        run_id=run_id,
        progress=progress,
    )
    record["config_snapshot"] = snapshot_for_run(config)
    return record


async def _run_via_testkube(config: dict[str, Any], *, triggered_by: str) -> dict[str, Any] | None:
    name = config.get("name", "k6-smoke").replace(" ", "-").lower()
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{settings.testkube_api_url.rstrip('/')}/v1/test-workflows/{name}/executions",
            json={"config": {"target": config.get("target_url")}},
        )
        if r.status_code >= 400:
            return None
        data = r.json()
        return {
            "id": data.get("id") or data.get("executionId"),
            "runner": "testkube",
            "triggered_by": triggered_by,
            "status": "running",
            "config_name": config.get("name"),
            "service": config.get("service"),
            "testkube_execution": data,
        }
