from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.config import settings
from app.run_store import get_run
from app.trace_store import load_traces_file, redact_headers, redact_trace


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root() -> Path:
    path = Path(settings.data_dir) / "payloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "default").strip())[:80]
    return cleaned.strip("-._") or "default"


def _index_path() -> Path:
    return _root() / "index.json"


def _read_index() -> list[dict[str, Any]]:
    path = _index_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _write_index(rows: list[dict[str, Any]]) -> None:
    _index_path().write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")


def _payload_dir(service: str, api_id: str) -> Path:
    d = _root() / service / api_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_path(service: str, api_id: str, name: str, version: int) -> Path:
    return _payload_dir(service, api_id) / f"{_safe_name(name)}.v{version}.json"


def _parse_query_from_url(url: str | None) -> dict[str, str]:
    if not url or "?" not in url:
        return {}
    qs = parse_qs(urlparse(url).query)
    return {k: (v[0] if v else "") for k, v in qs.items()}


def _parse_path_from_url(url: str | None, fallback: str | None = None) -> str:
    if not url:
        return fallback or ""
    path = urlparse(url).path or ""
    # strip service prefix like /analysis if present — keep as stored in trace
    return path or (fallback or "")


def list_payloads(
    *,
    service: str | None = None,
    api_id: str | None = None,
) -> list[dict[str, Any]]:
    rows = _read_index()
    out: list[dict[str, Any]] = []
    for row in rows:
        if service and row.get("service") != service:
            continue
        if api_id and row.get("api_id") != api_id:
            continue
        out.append(row)
    out.sort(key=lambda r: (r.get("service", ""), r.get("api_id", ""), r.get("name", ""), -(r.get("version") or 0)))
    return out


def get_payload(
    service: str,
    api_id: str,
    name: str = "default",
    version: int | None = None,
) -> dict[str, Any] | None:
    name = _safe_name(name)
    if version is not None:
        path = _file_path(service, api_id, name, version)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    # latest version for name
    latest = None
    for row in list_payloads(service=service, api_id=api_id):
        if row.get("name") == name:
            if latest is None or int(row.get("version") or 0) > int(latest.get("version") or 0):
                latest = row
    if not latest:
        return None
    return get_payload(service, api_id, name, int(latest["version"]))


def _next_version(service: str, api_id: str, name: str) -> int:
    name = _safe_name(name)
    versions = [
        int(r.get("version") or 0)
        for r in list_payloads(service=service, api_id=api_id)
        if r.get("name") == name
    ]
    return (max(versions) if versions else 0) + 1


def save_payload(record: dict[str, Any], *, bump: bool = True) -> dict[str, Any]:
    service = str(record.get("service") or "unknown")
    api_id = str(record.get("api_id") or "unknown")
    name = _safe_name(str(record.get("name") or "default"))
    version = int(record.get("version") or 0)
    if bump or version < 1:
        version = _next_version(service, api_id, name)
    record = {
        **record,
        "id": record.get("id") or str(uuid.uuid4()),
        "service": service,
        "api_id": api_id,
        "name": name,
        "version": version,
        "created_at": record.get("created_at") or _now(),
        "updated_at": _now(),
    }
    # redact secrets in stored request/response
    req = dict(record.get("request") or {})
    req["headers"] = redact_headers(req.get("headers"))
    resp = dict(record.get("response") or {})
    resp["headers"] = redact_headers(resp.get("headers"))
    record["request"] = req
    record["response"] = resp

    path = _file_path(service, api_id, name, version)
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")

    index = [
        r
        for r in _read_index()
        if not (r.get("service") == service and r.get("api_id") == api_id and r.get("name") == name and int(r.get("version") or 0) == version)
    ]
    index.append(
        {
            "id": record["id"],
            "service": service,
            "api_id": api_id,
            "name": name,
            "version": version,
            "created_at": record["created_at"],
            "source_run_id": record.get("source_run_id"),
            "method": (record.get("request") or {}).get("method"),
            "path": (record.get("request") or {}).get("path"),
            "status": (record.get("response") or {}).get("status"),
            "checks_passed": (record.get("meta") or {}).get("checks_passed"),
        }
    )
    _write_index(index)
    return record


def save_from_trace(
    run_id: str,
    api_id: str,
    *,
    name: str = "default",
    service: str | None = None,
) -> dict[str, Any]:
    run = get_run(run_id) or {}
    service = service or str(run.get("service") or "am-analysis")
    traces_path = Path(settings.data_dir) / "artifacts" / run_id / "traces.json"
    raw = None
    for row in load_traces_file(traces_path):
        if str(row.get("api_id")) == api_id:
            raw = row
            break
    if not raw:
        raise FileNotFoundError(f"No trace for run={run_id} api={api_id}")
    trace = redact_trace(raw)
    req = trace.get("request") or {}
    resp = trace.get("response") or {}
    path = _parse_path_from_url(trace.get("url"), fallback=trace.get("path"))
    query = _parse_query_from_url(trace.get("url"))
    record = {
        "service": service,
        "api_id": api_id,
        "name": name,
        "source_run_id": run_id,
        "request": {
            "method": trace.get("method") or "GET",
            "path": path,
            "headers": req.get("headers") or {},
            "query": query,
            "body": req.get("body"),
        },
        "response": {
            "status": resp.get("status"),
            "headers": resp.get("headers") or {},
            "body": resp.get("body"),
        },
        "meta": {
            "duration_ms": (trace.get("timings") or {}).get("duration_ms"),
            "checks_passed": trace.get("checks_passed"),
            "url": trace.get("url"),
        },
    }
    return save_payload(record, bump=True)


def payload_to_api_override(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert a saved payload into an api_overrides row for catalog merge."""
    req = payload.get("request") or {}
    return {
        "id": payload.get("api_id"),
        "method": req.get("method"),
        "path": req.get("path"),
        "headers": req.get("headers") or {},
        "query": req.get("query") or {},
        "body": req.get("body"),
    }


def delete_payload(service: str, api_id: str, name: str, version: int) -> bool:
    name = _safe_name(name)
    path = _file_path(service, api_id, name, version)
    existed = path.is_file()
    if existed:
        path.unlink()
    index = [
        r
        for r in _read_index()
        if not (
            r.get("service") == service
            and r.get("api_id") == api_id
            and r.get("name") == name
            and int(r.get("version") or 0) == version
        )
    ]
    _write_index(index)
    return existed


# --- Service-level payload sets (one version → many APIs) -----------------


def _sets_root(service: str) -> Path:
    d = _root() / "sets" / _safe_name(service)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sets_meta_path(service: str) -> Path:
    return _sets_root(service) / "meta.json"


def _set_file_path(service: str, version: int) -> Path:
    return _sets_root(service) / f"v{int(version)}.json"


def _read_sets_meta(service: str) -> dict[str, Any]:
    path = _sets_meta_path(service)
    if not path.is_file():
        return {"service": service, "active_version": None, "sets": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"service": service, "active_version": None, "sets": []}
    except json.JSONDecodeError:
        return {"service": service, "active_version": None, "sets": []}


def _write_sets_meta(service: str, meta: dict[str, Any]) -> None:
    _sets_meta_path(service).write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")


def _summarize_set(payload_set: dict[str, Any]) -> dict[str, Any]:
    apis = payload_set.get("apis") if isinstance(payload_set.get("apis"), dict) else {}
    return {
        "version": int(payload_set.get("version") or 0),
        "label": payload_set.get("label") or f"v{payload_set.get('version')}",
        "api_count": len(apis),
        "api_ids": sorted(apis.keys()),
        "created_at": payload_set.get("created_at"),
        "updated_at": payload_set.get("updated_at"),
    }


def list_payload_sets(service: str) -> dict[str, Any]:
    meta = _read_sets_meta(service)
    rows: list[dict[str, Any]] = []
    for entry in meta.get("sets") or []:
        ver = int(entry.get("version") or 0)
        if ver < 1:
            continue
        full = get_payload_set(service, ver)
        rows.append(_summarize_set(full) if full else entry)
    rows.sort(key=lambda r: -int(r.get("version") or 0))
    return {
        "service": service,
        "active_version": meta.get("active_version"),
        "sets": rows,
        "count": len(rows),
    }


def get_payload_set(service: str, version: int | None = None) -> dict[str, Any] | None:
    meta = _read_sets_meta(service)
    ver = version if version is not None else meta.get("active_version")
    if ver is None:
        sets = meta.get("sets") or []
        if not sets:
            return None
        ver = max(int(s.get("version") or 0) for s in sets)
    path = _set_file_path(service, int(ver))
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def create_payload_set(
    service: str,
    *,
    label: str | None = None,
    clone_from: int | None = None,
    make_active: bool = True,
) -> dict[str, Any]:
    meta = _read_sets_meta(service)
    existing = [int(s.get("version") or 0) for s in (meta.get("sets") or [])]
    next_ver = (max(existing) if existing else 0) + 1
    apis: dict[str, Any] = {}
    src_ver = clone_from
    if src_ver is None and existing:
        src_ver = meta.get("active_version") or max(existing)
    if src_ver is not None:
        src = get_payload_set(service, int(src_ver))
        if src and isinstance(src.get("apis"), dict):
            apis = json.loads(json.dumps(src["apis"]))  # deep copy
    now = _now()
    payload_set = {
        "id": str(uuid.uuid4()),
        "service": service,
        "version": next_ver,
        "label": (label or f"v{next_ver}").strip() or f"v{next_ver}",
        "created_at": now,
        "updated_at": now,
        "cloned_from": int(src_ver) if src_ver is not None else None,
        "apis": apis,
    }
    _set_file_path(service, next_ver).write_text(
        json.dumps(payload_set, indent=2, default=str), encoding="utf-8"
    )
    sets = [s for s in (meta.get("sets") or []) if int(s.get("version") or 0) != next_ver]
    sets.append(_summarize_set(payload_set))
    meta = {
        "service": service,
        "active_version": next_ver if make_active else meta.get("active_version"),
        "sets": sets,
    }
    if make_active or meta.get("active_version") is None:
        meta["active_version"] = next_ver
    _write_sets_meta(service, meta)
    return payload_set


def ensure_payload_set(service: str, *, label: str = "working") -> dict[str, Any]:
    existing = get_payload_set(service, None)
    if existing:
        return existing
    return create_payload_set(service, label=label, clone_from=None, make_active=True)


def set_active_payload_set(service: str, version: int) -> dict[str, Any]:
    payload_set = get_payload_set(service, version)
    if not payload_set:
        raise FileNotFoundError(f"Payload set {service} v{version} not found")
    meta = _read_sets_meta(service)
    meta["active_version"] = int(version)
    _write_sets_meta(service, meta)
    return {"service": service, "active_version": int(version), "set": _summarize_set(payload_set)}


def upsert_api_in_payload_set(
    service: str,
    api_id: str,
    *,
    version: int | None = None,
    request: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    name: str = "working",
    bump_set: bool = False,
) -> dict[str, Any]:
    """Register/update one API payload inside a service set.

    bump_set=True clones current set to a new version first, then writes the API there.
    """
    if bump_set:
        current = ensure_payload_set(service)
        payload_set = create_payload_set(
            service,
            label=None,
            clone_from=int(current.get("version") or 0),
            make_active=True,
        )
    else:
        if version is not None:
            payload_set = get_payload_set(service, version)
            if not payload_set:
                raise FileNotFoundError(f"Payload set {service} v{version} not found")
        else:
            payload_set = ensure_payload_set(service)

    req = dict(request or {})
    req["headers"] = redact_headers(req.get("headers"))
    resp = dict(response or {})
    resp["headers"] = redact_headers(resp.get("headers"))
    apis = dict(payload_set.get("apis") or {})
    apis[str(api_id)] = {
        "api_id": str(api_id),
        "name": _safe_name(name),
        "request": req,
        "response": resp,
        "meta": dict(meta or {}),
        "updated_at": _now(),
    }
    payload_set["apis"] = apis
    payload_set["updated_at"] = _now()
    ver = int(payload_set["version"])
    _set_file_path(service, ver).write_text(
        json.dumps(payload_set, indent=2, default=str), encoding="utf-8"
    )
    meta_doc = _read_sets_meta(service)
    sets = []
    for s in meta_doc.get("sets") or []:
        if int(s.get("version") or 0) == ver:
            sets.append(_summarize_set(payload_set))
        else:
            sets.append(s)
    if not any(int(s.get("version") or 0) == ver for s in sets):
        sets.append(_summarize_set(payload_set))
    meta_doc["sets"] = sets
    if meta_doc.get("active_version") is None:
        meta_doc["active_version"] = ver
    _write_sets_meta(service, meta_doc)
    return payload_set


def payload_set_to_refs(service: str, version: int | None = None) -> list[dict[str, Any]]:
    """Build execute payload_refs from a service set (synthetic refs pointing at set entries)."""
    payload_set = get_payload_set(service, version)
    if not payload_set:
        return []
    refs: list[dict[str, Any]] = []
    for api_id, entry in (payload_set.get("apis") or {}).items():
        refs.append(
            {
                "api_id": api_id,
                "name": (entry or {}).get("name") or "working",
                "set_version": int(payload_set.get("version") or 0),
                "from_set": True,
            }
        )
    return refs


def apply_payload_set(config: dict[str, Any], version: int | None = None) -> dict[str, Any]:
    """Merge an entire service payload set into config.payloads.api_overrides."""
    service = str(config.get("service") or "am-analysis")
    payload_set = get_payload_set(service, version)
    if not payload_set:
        return config
    cfg = dict(config)
    payloads = dict(cfg.get("payloads") or {})
    overrides = list(payloads.get("api_overrides") or [])
    by_id = {str(o.get("id")): o for o in overrides if o.get("id")}
    for api_id, entry in (payload_set.get("apis") or {}).items():
        if not isinstance(entry, dict):
            continue
        by_id[str(api_id)] = payload_to_api_override(
            {"api_id": api_id, "request": entry.get("request") or {}}
        )
    payloads["api_overrides"] = list(by_id.values())
    payloads["payload_set_version"] = int(payload_set.get("version") or 0)
    cfg["payloads"] = payloads
    return cfg


def apply_payload_refs(config: dict[str, Any], refs: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Merge named payload library entries into config.payloads.api_overrides."""
    if not refs:
        return config
    cfg = dict(config)
    payloads = dict(cfg.get("payloads") or {})
    overrides = list(payloads.get("api_overrides") or [])
    by_id = {str(o.get("id")): o for o in overrides if o.get("id")}
    service = str(cfg.get("service") or "am-analysis")
    for ref in refs:
        api_id = str(ref.get("api_id") or "")
        if not api_id:
            continue
        # Prefer service-set entry when set_version is present
        set_ver = ref.get("set_version")
        if set_ver is not None or ref.get("from_set"):
            payload_set = get_payload_set(service, int(set_ver) if set_ver is not None else None)
            entry = ((payload_set or {}).get("apis") or {}).get(api_id)
            if entry:
                by_id[api_id] = payload_to_api_override(
                    {"api_id": api_id, "request": entry.get("request") or {}}
                )
                continue
        name = str(ref.get("name") or "default")
        version = ref.get("version")
        version_i = int(version) if version is not None else None
        saved = get_payload(service, api_id, name, version_i)
        if not saved:
            continue
        by_id[api_id] = payload_to_api_override(saved)
    payloads["api_overrides"] = list(by_id.values())
    cfg["payloads"] = payloads
    return cfg
