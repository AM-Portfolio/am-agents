from __future__ import annotations

from typing import Any

from app.assets import K6_SCRIPT, PLAYWRIGHT_SCRIPT, read_text, sample_payloads
from app.auth_resolver import sanitize_auth_env
from app.catalog_loader import default_target_for_service
from app.config import settings
from app.run_store import save_config
from app.schemas import TestConfigIn


def default_config_dict() -> dict[str, Any]:
    service = "am-analysis"
    payloads = sample_payloads()
    return {
        "name": "am-analysis-dev-smoke",
        "description": "Dev POC — am-analysis dashboard APIs via in-cluster URL",
        "service": service,
        "environment": settings.default_environment,
        "test_type": "k6",
        "run_profile": "debug",
        "target_url": default_target_for_service(service, settings.default_environment),
        "payloads": {
            **payloads,
            "bench_run": {"vus": 1, "duration": "1s", "iterations": 1},
            "auth_env": {
                "username": settings.spt_auth_username,
            },
        },
        "scripts": {
            "k6": read_text(K6_SCRIPT),
            "playwright": read_text(PLAYWRIGHT_SCRIPT),
        },
    }


def ensure_default_config() -> dict[str, Any]:
    from app.run_store import list_configs

    configs = list_configs()
    for c in configs:
        if c.get("name") in ("am-analysis-dev-smoke", "default-smoke"):
            # Refresh target from .env / settings (local laptop vs cluster)
            c["target_url"] = default_target_for_service(
                c.get("service") or "am-analysis",
                c.get("environment") or settings.default_environment,
            )
            payloads = dict(c.get("payloads") or {})
            auth = dict(payloads.get("auth_env") or {})
            auth.setdefault("username", settings.spt_auth_username)
            payloads["auth_env"] = auth
            c["payloads"] = payloads
            return save_config(c)
    return save_config(default_config_dict())


def config_from_request(body: TestConfigIn | dict[str, Any]) -> dict[str, Any]:
    if isinstance(body, TestConfigIn):
        data = body.model_dump()
    else:
        data = dict(body)
    base = default_config_dict()
    service = data.get("service") or base.get("service") or "am-analysis"
    environment = data.get("environment") or base.get("environment") or settings.default_environment
    if data.get("target_url"):
        base["target_url"] = data["target_url"]
    else:
        base["target_url"] = default_target_for_service(service, environment)
    if data.get("name"):
        base["name"] = data["name"]
    for key in ("description", "service", "environment", "test_type", "run_profile", "openapi_version"):
        if data.get(key) is not None:
            base[key] = data[key]
    if data.get("payloads"):
        for key, val in data["payloads"].items():
            if val is not None:
                base["payloads"][key] = val
    if data.get("scripts"):
        base["scripts"].update(data["scripts"])
    return base


def snapshot_for_run(config: dict[str, Any]) -> dict[str, Any]:
    payloads = dict(config.get("payloads") or {})
    auth = sanitize_auth_env(payloads.get("auth_env"))
    if auth:
        payloads["auth_env"] = auth
    else:
        payloads.pop("auth_env", None)
    # Never persist secrets or generated k6 scripts in run history
    payloads.pop("k6_import", None)
    scripts = dict(config.get("scripts") or {})
    scripts.pop("k6", None)
    return {
        "config_id": config.get("id"),
        "config_name": config.get("name", "unnamed"),
        "service": config.get("service"),
        "environment": config.get("environment"),
        "test_type": config.get("test_type"),
        "run_profile": config.get("run_profile"),
        "target_url": config.get("target_url"),
        "payloads": payloads,
        "scripts": scripts,
    }
