"""IT-Support-agent display identity + multi-env helpers (lab|dev|preprod|prod)."""

from __future__ import annotations

import os
import re
from typing import Any


def agent_display_name() -> str:
    return (os.getenv("AGENT_DISPLAY_NAME") or "IT-Support-agent").strip() or "IT-Support-agent"


def normalize_alert_env(alert: dict[str, Any] | None = None, *, labels: dict[str, Any] | None = None) -> str:
    """
    Resolve env for routing/policy from alert labels (or namespace heuristics).

    Returns one of: lab | dev | preprod | prod | infra | unknown
    """
    alert = alert or {}
    labels = dict(labels or alert.get("labels") or {})
    raw = str(labels.get("env") or alert.get("env") or "").strip().lower()
    aliases = {
        "production": "prod",
        "prd": "prod",
        "pp": "preprod",
        "staging": "preprod",
        "stage": "preprod",
        "development": "dev",
        "local": "lab",
        "test": "lab",
    }
    if raw in aliases:
        raw = aliases[raw]
    if raw in {"lab", "dev", "preprod", "prod", "infra"}:
        return raw

    ns = str(labels.get("namespace") or "").strip().lower()
    if ns.startswith("infra-"):
        if "preprod" in ns:
            return "preprod"
        if ns.endswith("-prod") or ns.endswith("prod"):
            return "prod"
        if "dev" in ns:
            return "dev"
        return "infra"
    if "am-apps-prod" in ns or (ns.endswith("-prod") and "preprod" not in ns):
        return "prod"
    if "preprod" in ns or "am-apps-preprod" in ns:
        return "preprod"
    if "am-apps-dev" in ns or re.search(r"(^|-)dev($|-)", ns):
        return "dev"
    if ns in {"infra", "monitoring", "temporal"}:
        return "lab"
    return "unknown"


def ensure_env_label(alert: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow-copied alert with labels.env normalized."""
    out = dict(alert or {})
    labels = dict(out.get("labels") or {})
    env = normalize_alert_env(out, labels=labels)
    labels["env"] = env
    out["labels"] = labels
    out["env"] = env
    return out


def cliq_channel_for_env(env: str) -> str:
    """Map env → Cliq channel_ref (overridable via AGENT_CLIQ_CHANNEL_MAP JSON)."""
    import json

    raw = (os.getenv("AGENT_CLIQ_CHANNEL_MAP") or "").strip()
    if raw:
        try:
            mapping = {str(k).lower(): str(v) for k, v in json.loads(raw).items()}
            if env in mapping:
                return mapping[env]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    if env == "prod":
        return (os.getenv("AGENT_CLIQ_CHANNEL_PROD") or "cliq:prod").strip() or "cliq:prod"
    if env in {"lab", "dev", "preprod", "infra", "unknown"}:
        return (os.getenv("OPENPROJECT_NOTIFY_CHANNEL") or "cliq:lab").strip() or "cliq:lab"
    return "cliq:lab"


def auto_infra_envs() -> frozenset[str]:
    """Envs allowed to take auto_infra (default excludes prod until soak)."""
    raw = (os.getenv("AGENT_AUTO_INFRA_ENVS") or "lab,dev,preprod,infra,unknown").strip()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def verify_force_allowed(env: str) -> bool:
    """VERIFY_FORCE_RESULT only applies in lab (or when AGENT_VERIFY_FORCE_ENVS includes env)."""
    raw = (os.getenv("AGENT_VERIFY_FORCE_ENVS") or "lab").strip()
    allowed = frozenset(x.strip().lower() for x in raw.split(",") if x.strip())
    return env in allowed


def agent_prefix(*, env: str | None = None, decision: str | None = None) -> str:
    """User-facing stamp: [IT-Support-agent · env=preprod · auto_infra]."""
    parts = [agent_display_name()]
    if env:
        parts.append(f"env={env}")
    if decision:
        parts.append(str(decision))
    return "[" + " · ".join(parts) + "]"


def title_with_env(env: str, title: str) -> str:
    t = (title or "Alert").strip()
    if env and env != "unknown" and not t.lower().startswith(f"[{env}]"):
        return f"[{env}] {t}"[:255]
    return t[:255]
