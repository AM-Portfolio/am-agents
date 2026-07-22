from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.config import settings
from app.openapi_import import (
    default_openapi_path,
    fetch_openapi_sync,
    openapi_to_apis,
    openapi_url,
)

logger = logging.getLogger(__name__)

_CATALOG_ROOT = Path(__file__).resolve().parents[1] / "catalog"
_SERVICES_FILE = _CATALOG_ROOT / "services.yaml"


def _external_root() -> Path:
    raw = (
        os.environ.get("SPT_CATALOG_EXTERNAL")
        or settings.catalog_external_dir
        or "/catalog-external"
    )
    return Path(raw)


def _running_in_cluster() -> bool:
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST"))


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _iso_mtime(path: Path) -> str | None:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _git_line(repo: Path, *args: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), *args],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
        )
        line = (out or "").strip().splitlines()
        return line[0].strip() if line else None
    except Exception:
        return None


def _git_provenance(path: Path) -> dict[str, Any]:
    """Best-effort created/updated from git history for the registration file."""
    if not path.is_file():
        return {}
    repo = None
    cur = path.resolve().parent
    for _ in range(8):
        if (cur / ".git").exists():
            repo = cur
            break
        if cur.parent == cur:
            break
        cur = cur.parent
    if not repo:
        return {}
    try:
        rel = str(path.resolve().relative_to(repo))
    except ValueError:
        rel = str(path)
    last = _git_line(
        repo,
        "log",
        "-1",
        "--format=%an <%ae>|%cI|%h|%s",
        "--",
        rel,
    )
    first = _git_line(
        repo,
        "log",
        "--diff-filter=A",
        "--follow",
        "--format=%an <%ae>|%cI|%h|%s",
        "--",
        rel,
    )
    # Fallback: oldest commit touching the file
    if not first:
        first = _git_line(
            repo,
            "log",
            "--reverse",
            "--format=%an <%ae>|%cI|%h|%s",
            "--",
            rel,
        )

    def _parse(row: str | None) -> dict[str, str]:
        if not row or "|" not in row:
            return {}
        parts = row.split("|", 3)
        return {
            "author": parts[0] if len(parts) > 0 else "",
            "date": parts[1] if len(parts) > 1 else "",
            "commit": parts[2] if len(parts) > 2 else "",
            "subject": parts[3] if len(parts) > 3 else "",
        }

    last_p = _parse(last)
    first_p = _parse(first)
    out: dict[str, Any] = {"repo_root": str(repo), "git_path": rel}
    if first_p:
        out["git_created_by"] = first_p.get("author")
        out["git_created_at"] = first_p.get("date")
        out["git_created_commit"] = first_p.get("commit")
        out["git_created_subject"] = first_p.get("subject")
    if last_p:
        out["git_updated_by"] = last_p.get("author")
        out["git_updated_at"] = last_p.get("date")
        out["git_updated_commit"] = last_p.get("commit")
        out["git_updated_subject"] = last_p.get("subject")
    return out


def registration_file_for(service: str) -> Path | None:
    root = _external_root()
    candidates = [
        root / service / "spt.yaml",
        root / f"{service}.yaml",
        root / f"{service}.spt.yaml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    for path in list_registration_files():
        data = _read_yaml(path)
        sid = str(data.get("service") or "")
        if not sid and path.name == "spt.yaml":
            sid = path.parent.name
        if sid == service:
            return path
    return None


def build_registration_trace(service: str, reg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Owners, source, git/file dates, traces — for Specs UI tractability."""
    reg = reg if reg is not None else (load_registration(service) or {})
    path = registration_file_for(service)
    meta = reg.get("metadata") if isinstance(reg.get("metadata"), dict) else {}
    source = reg.get("source") if isinstance(reg.get("source"), dict) else {}
    if not source and isinstance(meta.get("source"), dict):
        source = meta["source"]
    traces = reg.get("traces")
    if traces is None:
        traces = meta.get("traces")
    if isinstance(traces, dict):
        traces = [{"name": k, "ref": v} for k, v in traces.items()]
    if not isinstance(traces, list):
        traces = []

    owners = reg.get("owners") or meta.get("owners") or []
    if isinstance(owners, str):
        owners = [owners]

    git = _git_provenance(path) if path else {}
    file_mtime = _iso_mtime(path) if path else None

    created_by = (
        reg.get("createdBy")
        or meta.get("createdBy")
        or git.get("git_created_by")
        or (owners[0] if owners else None)
    )
    updated_by = (
        reg.get("updatedBy")
        or meta.get("updatedBy")
        or git.get("git_updated_by")
        or created_by
    )
    created_at = (
        reg.get("createdAt")
        or meta.get("createdAt")
        or git.get("git_created_at")
    )
    updated_at = (
        reg.get("updatedAt")
        or meta.get("updatedAt")
        or git.get("git_updated_at")
        or file_mtime
    )

    repo = source.get("repo") or ("am-core-services" if path and "am-core-services" in str(path) else None)
    rel_path = source.get("path")
    if not rel_path and path:
        rel_path = git.get("git_path") or str(path)

    default_traces = [
        {"name": "configmap", "ref": f"spt-catalog-{service}"},
        {"name": "onboarding", "ref": "docs/spt-onboarding.md"},
        {"name": "namespace", "ref": "load-testing"},
    ]
    # YAML traces first, then defaults for missing names
    seen_names = {str(t.get("name")) for t in traces if isinstance(t, dict)}
    for t in default_traces:
        if t["name"] not in seen_names:
            traces.append(t)

    return {
        "service": service,
        "label": reg.get("label") or service,
        "owners": owners,
        "registered_by": created_by,
        "created_by": created_by,
        "updated_by": updated_by,
        "created_at": created_at,
        "updated_at": updated_at,
        "file_mtime": file_mtime,
        "file_path": str(path) if path else None,
        "file_bytes": path.stat().st_size if path and path.is_file() else None,
        "registration_source": "registration" if path else ("baked" if not reg else "unknown"),
        "source": {
            "repo": repo,
            "path": rel_path,
            "configmap": f"spt-catalog-{service}",
            "kind": reg.get("kind") or "ServiceLoadTest",
            "apiVersion": reg.get("apiVersion") or "am.spt/v1",
        },
        "traces": traces,
        "git": {k: v for k, v in git.items() if k != "repo_root"} if git else {},
        "runtime": reg.get("runtime"),
        "enabled": reg.get("enabled", True),
        "description": reg.get("description") or meta.get("description"),
        "tags": reg.get("tags") or meta.get("tags") or [],
    }


def list_registration_files() -> list[Path]:
    """spt.yaml files under catalog-external/<service>/spt.yaml (and flat *.yaml)."""
    root = _external_root()
    found: list[Path] = []
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("spt.yaml")):
        found.append(path)
    for path in sorted(root.glob("*.yaml")):
        if path.name != "spt.yaml" and path not in found:
            # flat ConfigMap mount style: /catalog-external/am-analysis.yaml
            found.append(path)
    return found


def load_registration(service: str) -> dict[str, Any] | None:
    """Load ServiceLoadTest registration for a service id."""
    root = _external_root()
    candidates = [
        root / service / "spt.yaml",
        root / f"{service}.yaml",
        root / f"{service}.spt.yaml",
    ]
    for path in candidates:
        data = _read_yaml(path)
        if not data:
            continue
        if data.get("enabled") is False:
            return None
        data.setdefault("service", service)
        return data
    for path in list_registration_files():
        data = _read_yaml(path)
        if not data or data.get("enabled") is False:
            continue
        sid = str(data.get("service") or "")
        if not sid and path.name == "spt.yaml":
            sid = path.parent.name
        if sid == service:
            data.setdefault("service", service)
            return data
    return None


def _registration_to_service_row(reg: dict[str, Any]) -> dict[str, Any]:
    service = str(reg.get("service") or "")
    targets = reg.get("targets") or {}
    row: dict[str, Any] = {
        "id": service,
        "label": reg.get("label") or service,
        "runtime": reg.get("runtime") or "java",
        "targets": targets,
        "openapi": reg.get("openapi") or {},
        "source": "registration",
    }
    # Back-compat fields used by older default_target helpers
    if isinstance(targets, dict):
        if targets.get("dev"):
            row["default_target_url_dev"] = targets["dev"]
        if targets.get("preprod"):
            row["default_target_url_preprod"] = targets["preprod"]
        if targets.get("prod"):
            row["default_target_url_prod"] = targets["prod"]
        if targets.get("public_dev"):
            row["public_target_url_dev"] = targets["public_dev"]
    return row


def load_catalog() -> dict[str, Any]:
    baked = _read_yaml(_SERVICES_FILE) if _SERVICES_FILE.is_file() else {}
    services_by_id: dict[str, dict[str, Any]] = {}
    for row in baked.get("services") or []:
        if isinstance(row, dict) and row.get("id"):
            services_by_id[str(row["id"])] = dict(row)

    for path in list_registration_files():
        reg = _read_yaml(path)
        if not reg or reg.get("enabled") is False:
            continue
        sid = str(reg.get("service") or "")
        if not sid and path.name == "spt.yaml":
            sid = path.parent.name
        if not sid:
            continue
        reg.setdefault("service", sid)
        services_by_id[sid] = _registration_to_service_row(reg)

    environments = baked.get("environments") or ["dev", "preprod", "prod"]
    load_presets = baked.get("load_presets") or {"smoke": {"vus": 3, "duration": "30s"}}
    return {
        "services": list(services_by_id.values()),
        "environments": environments,
        "load_presets": load_presets,
    }


def service_apis_path(service: str) -> Path:
    return _CATALOG_ROOT / service / "apis.yaml"


def service_meta(service: str) -> dict[str, Any]:
    catalog = load_catalog()
    for row in catalog.get("services") or []:
        if row.get("id") == service:
            return row
    reg = load_registration(service)
    if reg:
        return _registration_to_service_row(reg)
    return {}


def default_target_for_service(service: str, environment: str = "dev") -> str:
    """Resolve base URL from registration targets[env], then legacy fields, then POC default.

    Outside the cluster, prefer public_{env} so local k6 can reach the service
    (cluster .svc.cluster.local DNS is not resolvable on a laptop).
    """
    env = (environment or "dev").lower()

    reg = load_registration(service) or {}
    targets = reg.get("targets") if isinstance(reg.get("targets"), dict) else {}
    meta = service_meta(service)
    meta_targets = meta.get("targets") if isinstance(meta.get("targets"), dict) else {}

    def _pick(*candidates: Any) -> str | None:
        for c in candidates:
            if isinstance(c, str) and c.startswith("http"):
                return c.rstrip("/")
        return None

    if not _running_in_cluster():
        public = _pick(
            targets.get(f"public_{env}"),
            targets.get("public"),
            meta_targets.get(f"public_{env}"),
            meta.get(f"public_target_url_{env}"),
        )
        if public:
            return public
        # Non-cluster private target (rare)
        private = _pick(targets.get(env), meta_targets.get(env))
        if private and ".svc.cluster.local" not in private:
            return private
        if service == "am-analysis" and settings.poc_target_url:
            poc = str(settings.poc_target_url).rstrip("/")
            if ".svc.cluster.local" not in poc:
                return poc
        # Fall through — may still be cluster URL (will fail locally; better than silent wrong public)

    picked = _pick(
        targets.get(env),
        meta_targets.get(env),
        meta.get(f"default_target_url_{env}"),
        meta.get("default_target_url_dev") if env == "dev" else None,
        meta.get("default_target_url"),
    )
    if picked:
        return picked

    if service == "am-analysis" and settings.poc_target_url:
        return settings.poc_target_url.rstrip("/")
    return settings.poc_target_url.rstrip("/")


def reachable_target_for_service(service: str, environment: str, current: str | None = None) -> str:
    """Rewrite cluster-only targets to public_* when SPT runs outside Kubernetes."""
    env = (environment or "dev").lower()
    cur = (current or "").rstrip("/")
    if _running_in_cluster():
        return cur or default_target_for_service(service, env)
    if cur and ".svc.cluster.local" not in cur and cur.startswith("http"):
        return cur
    return default_target_for_service(service, env)


def _health_api() -> dict[str, Any]:
    return {
        "id": "actuator.health",
        "name": "GET /actuator/health",
        "method": "GET",
        "path": "/actuator/health",
        "headers": {"Accept": "application/json"},
        "query": {},
        "body": None,
        "checks": ["status_2xx"],
        "source": "convention",
    }


_token_cache: dict[str, Any] = {"token": None, "at": 0.0}
_TOKEN_TTL_SEC = 240.0
_openapi_doc_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_OPENAPI_DOC_TTL_SEC = 90.0


def _platform_openapi_headers() -> dict[str, str]:
    """SPT owns auth — use identity login when fetching protected OpenAPI docs."""
    username = settings.spt_auth_username
    password = settings.spt_auth_password
    if not username or not password:
        return {}
    now = time.time()
    cached = _token_cache.get("token")
    if cached and (now - float(_token_cache.get("at") or 0)) < _TOKEN_TTL_SEC:
        return {"Authorization": f"Bearer {cached}", "Accept": "application/json"}
    try:
        url = f"{settings.spt_identity_url.rstrip('/')}/auth/login"
        with httpx.Client(timeout=12.0) as client:
            resp = client.post(url, json={"username": username, "password": password})
            resp.raise_for_status()
            token = (resp.json() or {}).get("access_token")
        if not token:
            return {}
        _token_cache["token"] = token
        _token_cache["at"] = now
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    except Exception as exc:
        logger.warning("OpenAPI auth login failed: %s", exc)
        return {}


def platform_bearer_token() -> str | None:
    """Access token from platform identity (for Swagger Try it out)."""
    headers = _platform_openapi_headers()
    auth = headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    # Do not forward browser Accept-Encoding: upstream may return gzip/br while we
    # drop Content-Encoding on the way back → UI shows binary garbage.
    "accept-encoding",
    "content-encoding",
}


def _decode_proxied_body(raw: bytes, content_encoding: str | None = None) -> bytes:
    """Ensure try-proxy returns plain bytes (JSON/text), not gzip/br."""
    if not raw:
        return raw
    import gzip
    import io
    import zlib

    enc = (content_encoding or "").lower().strip()
    encodings = [e.strip() for e in enc.split(",") if e.strip()] if enc else []
    data = raw

    def try_gzip(buf: bytes) -> bytes | None:
        try:
            return gzip.GzipFile(fileobj=io.BytesIO(buf)).read()
        except Exception:
            return None

    def try_deflate(buf: bytes) -> bytes | None:
        try:
            return zlib.decompress(buf)
        except Exception:
            try:
                return zlib.decompress(buf, -zlib.MAX_WBITS)
            except Exception:
                return None

    def try_brotli(buf: bytes) -> bytes | None:
        try:
            import brotli  # type: ignore

            return brotli.decompress(buf)
        except Exception:
            return None

    for e in encodings:
        if e in ("gzip", "x-gzip"):
            out = try_gzip(data)
            if out is not None:
                data = out
        elif e == "deflate":
            out = try_deflate(data)
            if out is not None:
                data = out
        elif e in ("br", "brotli"):
            out = try_brotli(data)
            if out is not None:
                data = out

    # Magic-byte fallback when Content-Encoding was dropped by an edge
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        out = try_gzip(data)
        if out is not None:
            data = out
    elif len(data) >= 2 and data[0:2] in (b"\x78\x01", b"\x78\x9c", b"\x78\xda"):
        out = try_deflate(data)
        if out is not None:
            data = out

    return data


async def proxy_try_request(
    service: str,
    environment: str,
    method: str,
    path: str,
    *,
    query: str = "",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> dict[str, Any]:
    """Forward a Swagger Try-it-out call to a registered service target (avoids browser CORS)."""
    env = (environment or settings.default_environment or "dev").lower()
    reg = load_registration(service) or {}
    bases = _try_base_candidates(service, env, reg)
    if not bases:
        return {
            "ok": False,
            "status_code": 502,
            "error": f"No try targets for {service}/{env}",
            "upstream_url": None,
            "headers": {"content-type": "application/json"},
            "body": b'{"detail":"No try targets configured"}',
        }

    fwd: dict[str, str] = {}
    for k, v in (headers or {}).items():
        lk = str(k).lower()
        if lk in _HOP_BY_HOP or lk.startswith("x-forwarded"):
            continue
        fwd[k] = v
    # Prefer plain responses so Overview/Swagger can display JSON
    fwd["Accept-Encoding"] = "identity"
    if "Authorization" not in fwd and "authorization" not in {x.lower() for x in fwd}:
        auth = _platform_openapi_headers().get("Authorization")
        if auth:
            fwd["Authorization"] = auth
    if "Accept" not in fwd and "accept" not in {x.lower() for x in fwd}:
        fwd["Accept"] = "*/*"

    rel = "/" + str(path or "").lstrip("/")
    if rel == "/":
        rel = ""
    q = ("?" + query) if query else ""
    last_err = "no bases"
    last_url = ""
    # Generous but bounded — Cloudflare often 524s around 100s; keep UI usable
    timeout = httpx.Timeout(45.0, connect=10.0)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for base in bases:
            url = f"{base.rstrip('/')}{rel}{q}"
            last_url = url
            try:
                resp = await client.request(method.upper(), url, headers=fwd, content=body)
                ctype = resp.headers.get("content-type") or "application/octet-stream"
                raw = _decode_proxied_body(
                    resp.content,
                    resp.headers.get("content-encoding"),
                )
                out_headers = {
                    "content-type": ctype,
                    "x-spt-upstream": url,
                    "x-spt-try-base": base,
                }
                corr = resp.headers.get("x-correlation-id")
                if corr:
                    out_headers["x-correlation-id"] = corr
                return {
                    "ok": True,
                    "status_code": resp.status_code,
                    "upstream_url": url,
                    "headers": out_headers,
                    "body": raw,
                }
            except httpx.TimeoutException as exc:
                last_err = f"timeout after 45s ({type(exc).__name__})"
                logger.info("Try proxy timeout %s %s: %s", service, url, exc)
            except Exception as exc:
                last_err = str(exc) or type(exc).__name__
                logger.info("Try proxy failed %s %s: %s", service, url, exc)

    status = 504 if "timeout" in last_err else 502
    detail = {
        "detail": f"Upstream unreachable: {last_err}",
        "tried": bases,
        "last_url": last_url,
        "hint": "Browser hits localhost SPT proxy; SPT forwards to public_*/cluster target for the selected env.",
    }
    return {
        "ok": False,
        "status_code": status,
        "error": last_err,
        "upstream_url": last_url,
        "headers": {
            "content-type": "application/json",
            "x-spt-upstream": last_url or "",
            "x-spt-try-base": (bases[0] if bases else ""),
        },
        "body": json.dumps(detail).encode("utf-8"),
    }


def _try_base_candidates(service: str, environment: str, reg: dict[str, Any]) -> list[str]:
    """Bases for browser Try-it-out. Prefer public_* path prefix from spt.yaml (e.g. …/analysis)."""
    env = (environment or "dev").lower()
    targets = reg.get("targets") if isinstance(reg.get("targets"), dict) else {}
    bases: list[str] = []

    def add(url: str | None) -> None:
        if not isinstance(url, str) or not url.startswith("http"):
            return
        u = url.rstrip("/")
        if u.startswith("http://") and ("asrax.in" in u or "localhost" not in u):
            u = "https://" + u[len("http://") :]
        # Local SPT cannot resolve in-cluster DNS
        if (not _running_in_cluster()) and ".svc.cluster.local" in u:
            return
        if u not in bases:
            bases.append(u)

    if _running_in_cluster():
        add(default_target_for_service(service, env))

    # Prefer this env's public_* only (no public_dev fallback for other envs)
    add(targets.get(f"public_{env}"))
    add(targets.get("public"))

    if env == "dev" and service == "am-analysis" and settings.poc_target_url:
        add(settings.poc_target_url)

    if not _running_in_cluster():
        add(default_target_for_service(service, env))

    return bases


def _apis_from_openapi_registration(
    reg: dict[str, Any],
    *,
    environment: str,
) -> dict[str, Any]:
    service = str(reg.get("service") or "")
    runtime = str(reg.get("runtime") or "java").lower()
    oas = reg.get("openapi") if isinstance(reg.get("openapi"), dict) else {}
    preferred = str(oas.get("path") or default_openapi_path(runtime))
    path_candidates: list[str] = []
    for p in (preferred, default_openapi_path(runtime), "/v3/api-docs", "/api-docs", "/openapi.json"):
        if p and p not in path_candidates:
            path_candidates.append(p)

    bases = _openapi_base_candidates(service, environment, reg)
    if not bases:
        return {
            "base_url": "{{target_url}}",
            "apis": [_health_api()],
            "source": "registration",
            "openapi_error": "no target",
            "openapi_version": None,
        }

    headers = _platform_openapi_headers()
    last_err: Exception | None = None
    last_url = ""
    primary = bases[0]
    for target in bases:
        for path in path_candidates:
            url = openapi_url(target, path)
            last_url = url
            try:
                doc = fetch_openapi_sync(url, headers=headers, timeout=12.0)
                apis = openapi_to_apis(doc)
                ids = {a.get("id") for a in apis}
                if "actuator.health" not in ids and not any(
                    str(a.get("path") or "").endswith("/actuator/health") for a in apis
                ):
                    apis.insert(0, _health_api())
                info = doc.get("info") if isinstance(doc.get("info"), dict) else {}
                return {
                    "base_url": "{{target_url}}",
                    "apis": apis,
                    "source": "openapi",
                    "openapi_url": url,
                    "openapi_version": info.get("version"),
                    "openapi_title": info.get("title"),
                    "runtime": runtime,
                    "count": len(apis),
                    "resolved_target": target,
                    "cluster_target": primary,
                }
            except Exception as exc:
                last_err = exc
                logger.info("OpenAPI try failed for %s (%s): %s", service, url, exc)

    logger.warning("OpenAPI fetch failed for %s after %s: %s", service, path_candidates, last_err)
    baked = _load_baked_apis(service)
    if baked.get("apis"):
        baked["source"] = "baked-fallback"
        baked["openapi_error"] = str(last_err)
        baked["openapi_url"] = last_url
        baked["openapi_version"] = None
        baked["runtime"] = runtime
        return baked
    return {
        "base_url": "{{target_url}}",
        "apis": [_health_api()],
        "source": "health-fallback",
        "openapi_url": last_url,
        "openapi_error": str(last_err),
        "openapi_version": None,
        "runtime": runtime,
    }


def _openapi_base_candidates(service: str, environment: str, reg: dict[str, Any]) -> list[str]:
    """Prefer browser-reachable public_* when outside the cluster (avoid slow .svc DNS fail)."""
    env = (environment or "dev").lower()
    bases: list[str] = []
    primary = default_target_for_service(service, env)
    targets = reg.get("targets") if isinstance(reg.get("targets"), dict) else {}

    def add(url: str | None) -> None:
        if not isinstance(url, str) or not url.startswith("http"):
            return
        u = url.rstrip("/")
        if (not _running_in_cluster()) and ".svc.cluster.local" in u:
            return
        if u not in bases:
            bases.append(u)

    if _running_in_cluster():
        add(primary)
    # Only this env's public_* (do not fall back to public_dev for preprod/prod)
    add(targets.get(f"public_{env}"))
    add(targets.get("public"))
    if env == "dev" and service == "am-analysis" and settings.poc_target_url:
        add(settings.poc_target_url)
    if _running_in_cluster():
        pass
    else:
        add(primary)
    return bases


def _registration_payload(service: str, reg: dict[str, Any], oas: dict[str, Any], runtime: str) -> dict[str, Any]:
    return {
        "apiVersion": reg.get("apiVersion"),
        "kind": reg.get("kind"),
        "service": reg.get("service") or service,
        "label": reg.get("label") or service,
        "enabled": reg.get("enabled", True),
        "runtime": runtime,
        "owners": reg.get("owners"),
        "targets": reg.get("targets") or {},
        "openapi": oas,
        "description": reg.get("description"),
        "tags": reg.get("tags") or [],
        "createdBy": reg.get("createdBy"),
        "updatedBy": reg.get("updatedBy"),
        "createdAt": reg.get("createdAt"),
        "updatedAt": reg.get("updatedAt"),
        "source": reg.get("source"),
        "traces": reg.get("traces"),
        "metadata": reg.get("metadata"),
        "trace": build_registration_trace(service, reg),
    }


def load_openapi_document(
    service: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Fetch live OpenAPI JSON for UI (Swagger-style viewer) + registration metadata."""
    env = environment or settings.default_environment
    cache_key = f"{service}|{env}"
    hit = _openapi_doc_cache.get(cache_key)
    if hit and (time.time() - hit[0]) < _OPENAPI_DOC_TTL_SEC:
        return hit[1]

    reg = load_registration(service) or {}
    runtime = str(reg.get("runtime") or "java").lower()
    oas = reg.get("openapi") if isinstance(reg.get("openapi"), dict) else {}
    preferred = str(oas.get("path") or default_openapi_path(runtime))
    path_candidates: list[str] = []
    for p in (preferred, default_openapi_path(runtime), "/v3/api-docs", "/api-docs", "/openapi.json"):
        if p and p not in path_candidates:
            path_candidates.append(p)

    bases = _openapi_base_candidates(service, env, reg)
    headers = _platform_openapi_headers()
    last_err: str | None = None
    last_url = ""
    primary_target = bases[0] if bases else default_target_for_service(service, env)

    for target in bases:
        for path in path_candidates:
            if not target:
                break
            url = openapi_url(target, path)
            last_url = url
            try:
                doc = fetch_openapi_sync(url, headers=headers, timeout=12.0)
                info = doc.get("info") if isinstance(doc.get("info"), dict) else {}
                paths = doc.get("paths") if isinstance(doc.get("paths"), dict) else {}
                result = {
                    "service": service,
                    "environment": env,
                    "runtime": runtime,
                    "target_url": target,
                    "openapi_url": url,
                    "openapi_url_cluster": openapi_url(primary_target, path) if primary_target else url,
                    "openapi_path": path,
                    "ok": True,
                    "openapi": str(doc.get("openapi") or doc.get("swagger") or ""),
                    "title": info.get("title"),
                    "version": info.get("version"),
                    "description": info.get("description"),
                    "servers": doc.get("servers") or [],
                    "path_count": len(paths),
                    "operation_count": sum(
                        1
                        for item in paths.values()
                        if isinstance(item, dict)
                        for m in ("get", "post", "put", "patch", "delete", "head", "options")
                        if m in item
                    ),
                    "document": doc,
                    "registration": _registration_payload(service, reg, oas, runtime),
                }
                _openapi_doc_cache[cache_key] = (time.time(), result)
                return result
            except Exception as exc:
                last_err = str(exc)
                logger.info("OpenAPI document fetch failed %s %s: %s", service, url, exc)

    result = {
        "service": service,
        "environment": env,
        "runtime": runtime,
        "target_url": primary_target,
        "openapi_url": last_url,
        "openapi_url_cluster": last_url,
        "ok": False,
        "error": last_err or "no target or OpenAPI unavailable",
        "document": None,
        "registration": _registration_payload(service, reg, oas, runtime),
    }
    _openapi_doc_cache[cache_key] = (time.time() - (_OPENAPI_DOC_TTL_SEC - 15), result)
    return result


def list_registered_services() -> list[dict[str, Any]]:
    """Summary rows for Specs UI sidebar (configured registrations)."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in list_registration_files():
        reg = _read_yaml(path)
        if not reg or reg.get("enabled") is False:
            continue
        sid = str(reg.get("service") or "")
        if not sid and path.name == "spt.yaml":
            sid = path.parent.name
        if not sid or sid in seen:
            continue
        seen.add(sid)
        runtime = str(reg.get("runtime") or "java")
        oas = reg.get("openapi") if isinstance(reg.get("openapi"), dict) else {}
        targets = reg.get("targets") if isinstance(reg.get("targets"), dict) else {}
        rows.append(
            {
                "id": sid,
                "label": reg.get("label") or sid,
                "runtime": runtime,
                "openapi_path": oas.get("path") or default_openapi_path(runtime),
                "targets": targets,
                "owners": reg.get("owners"),
                "apiVersion": reg.get("apiVersion") or "am.spt/v1",
                "source": "registration",
                "trace": build_registration_trace(sid, reg),
            }
        )
    # Also surface catalog services that have baked apis but no registration
    for svc in load_catalog().get("services") or []:
        sid = str(svc.get("id") or "")
        if not sid or sid in seen:
            continue
        baked = _load_baked_apis(sid)
        if not baked.get("apis"):
            continue
        seen.add(sid)
        rows.append(
            {
                "id": sid,
                "label": svc.get("label") or sid,
                "runtime": svc.get("runtime") or "unknown",
                "openapi_path": None,
                "targets": svc.get("targets") or {},
                "owners": None,
                "apiVersion": None,
                "source": "baked",
                "trace": build_registration_trace(sid, {}),
            }
        )
    return rows


def openapi_versions_by_env(service: str) -> list[dict[str, Any]]:
    """Probe each configured env for OpenAPI info.version (quick metadata, no full doc)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    reg = load_registration(service) or {}
    targets = reg.get("targets") if isinstance(reg.get("targets"), dict) else {}
    envs = [e for e in ("dev", "preprod", "prod") if targets.get(e) or targets.get(f"public_{e}")]
    if not envs:
        envs = [settings.default_environment]
    out_map: dict[str, dict[str, Any]] = {}

    def _one(env: str) -> tuple[str, dict[str, Any]]:
        bases = _openapi_base_candidates(service, env, reg)
        if not bases:
            return env, {
                "id": f"{env}|unknown",
                "environment": env,
                "ok": False,
                "target_url": None,
                "openapi_url": None,
                "openapi": None,
                "title": None,
                "version": None,
                "path_count": None,
                "operation_count": None,
                "error": "No public target for this env (set public_"+env+" in spt.yaml)",
                "label": f"{env} - no public target",
            }
        meta = load_openapi_document(service, env)
        ver = meta.get("version")
        return env, {
            "id": f"{env}|{ver or 'unknown'}",
            "environment": env,
            "ok": bool(meta.get("ok")),
            "target_url": meta.get("target_url"),
            "openapi_url": meta.get("openapi_url"),
            "openapi": meta.get("openapi"),
            "title": meta.get("title"),
            "version": ver,
            "path_count": meta.get("path_count"),
            "operation_count": meta.get("operation_count"),
            "error": meta.get("error"),
            "label": (
                f"{env} - API {ver} - {meta.get('operation_count') or 0} ops"
                if meta.get("ok")
                else f"{env} - unreachable"
            ),
        }

    with ThreadPoolExecutor(max_workers=min(3, len(envs))) as pool:
        futs = [pool.submit(_one, env) for env in envs]
        for fut in as_completed(futs):
            env, row = fut.result()
            out_map[env] = row
    return [out_map[e] for e in envs if e in out_map]


def _load_baked_apis(service: str) -> dict[str, Any]:
    path = service_apis_path(service)
    if not path.is_file():
        return {"base_url": None, "apis": []}
    data = _read_yaml(path)
    apis = data.get("apis") or []
    if not isinstance(apis, list):
        apis = []
    return {"base_url": data.get("base_url"), "apis": apis, "source": "baked"}


def load_service_apis(service: str, environment: str | None = None) -> dict[str, Any]:
    """
    Prefer external spt.yaml + live OpenAPI; fall back to baked catalog/<service>/apis.yaml.
    """
    env = environment or settings.default_environment
    reg = load_registration(service)
    if reg and (reg.get("openapi") is not None or reg.get("runtime")):
        return _apis_from_openapi_registration(reg, environment=env)
    # Registration with explicit apis (escape hatch) — still no auth block required
    if reg and isinstance(reg.get("apis"), list) and reg["apis"]:
        return {
            "base_url": "{{target_url}}",
            "apis": reg["apis"],
            "source": "registration-apis",
            "runtime": reg.get("runtime"),
        }
    return _load_baked_apis(service)


def list_service_api_ids(service: str, environment: str | None = None) -> list[str]:
    return [
        str(a.get("id"))
        for a in load_service_apis(service, environment).get("apis", [])
        if a.get("id")
    ]


def _substitute(value: str, ctx: dict[str, str], env_ctx: dict[str, str] | None = None) -> str:
    out = value
    for key, val in (env_ctx or {}).items():
        out = out.replace(f"{{{{env.{key}}}}}", val)
    for key, val in ctx.items():
        out = out.replace(f"{{{{{key}}}}}", val)
    return out


def build_env_ctx(config: dict[str, Any]) -> dict[str, str]:
    payloads = config.get("payloads") or {}
    auth = payloads.get("auth_env") or {}
    token = str(auth.get("token") or os.environ.get("SPT_AUTH_TOKEN") or "")
    if token and not token.lower().startswith("bearer "):
        token = f"Bearer {token}"
    return {
        "SPT_AUTH_TOKEN": token,
        "SPT_USER_ID": str(auth.get("user_id") or os.environ.get("SPT_USER_ID") or settings.spt_user_id),
    }


def resolve_api(api: dict[str, Any], ctx: dict[str, str], env_ctx: dict[str, str]) -> dict[str, Any]:
    resolved = dict(api)
    resolved["name"] = _substitute(str(api.get("name", api.get("id", ""))), ctx, env_ctx)
    resolved["path"] = _substitute(str(api.get("path", "/")), ctx, env_ctx)
    headers = {}
    for k, v in (api.get("headers") or {}).items():
        val = _substitute(str(v), ctx, env_ctx)
        if val:
            headers[str(k)] = val
    # Platform OpenAPI often omits securitySchemes; still inject JWT when we have one
    token = str(env_ctx.get("SPT_AUTH_TOKEN") or "").strip()
    if token and not any(str(k).lower() == "authorization" for k in headers):
        headers["Authorization"] = token
    resolved["headers"] = headers
    query: dict[str, str] = {}
    for k, v in (api.get("query") or {}).items():
        val = _substitute(str(v), ctx, env_ctx)
        if val:
            query[str(k)] = val
    resolved["query"] = query
    if api.get("body") is not None:
        resolved["body"] = _substitute(str(api["body"]), ctx, env_ctx)
    else:
        resolved["body"] = None
    resolved["method"] = str(api.get("method", "GET")).upper()
    resolved["checks"] = list(api.get("checks") or ["status_2xx"])
    return resolved


def merge_api_overrides(
    apis: list[dict[str, Any]],
    overrides: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not overrides:
        return apis
    by_id = {str(o.get("id")): o for o in overrides if o.get("id")}
    merged: list[dict[str, Any]] = []
    for api in apis:
        aid = str(api.get("id", ""))
        if aid in by_id:
            patch = by_id[aid]
            row = dict(api)
            for k, v in patch.items():
                if v is None:
                    continue
                if k == "headers" and isinstance(v, dict):
                    # Empty override headers must not wipe catalog Authorization
                    base_h = dict(api.get("headers") or {})
                    if v:
                        base_h.update({str(hk): hv for hk, hv in v.items() if hv is not None and hv != ""})
                    row["headers"] = base_h
                elif k == "query" and isinstance(v, dict):
                    base_q = dict(api.get("query") or {})
                    base_q.update({str(qk): qv for qk, qv in v.items() if qv is not None})
                    row["query"] = base_q
                else:
                    row[k] = v
            merged.append(row)
        else:
            merged.append(api)
    return merged


def resolve_base_url(config: dict[str, Any], catalog_base: str | None, ctx: dict[str, str]) -> str:
    raw = _substitute(str(catalog_base or "{{target_url}}"), ctx).rstrip("/")
    if raw:
        return raw
    target = (ctx.get("target_url") or settings.poc_target_url or "").rstrip("/")
    return target


def apis_for_config(
    config: dict[str, Any],
    *,
    run_id: str = "",
    api_ids: list[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    service = config.get("service") or "am-analysis"
    environment = config.get("environment") or settings.default_environment
    catalog = load_service_apis(service, environment)
    payloads = config.get("payloads") or {}
    api_overrides = payloads.get("api_overrides") or []
    env_ctx = build_env_ctx(config)
    target = reachable_target_for_service(
        service,
        environment,
        config.get("target_url") or default_target_for_service(service, environment),
    )
    # Keep config aligned so run records show the URL k6 actually hits
    config["target_url"] = target
    ctx = {
        "target_url": target,
        "run_id": run_id,
        "service": service,
    }
    base_url = resolve_base_url(config, catalog.get("base_url"), ctx)
    apis = merge_api_overrides(catalog.get("apis") or [], api_overrides)
    selected = api_ids if api_ids is not None else config.get("selected_api_ids")
    if selected:
        want = {str(x) for x in selected if x}
        apis = [a for a in apis if str(a.get("id")) in want]
        found = {str(a.get("id")) for a in apis if a.get("id")}
        missing = sorted(want - found)
        if missing:
            raise ValueError(f"Unknown api_id(s) for service {service}: {', '.join(missing)}")
    return base_url, [resolve_api(a, ctx, env_ctx) for a in apis if a.get("id")]


def apply_preset(config: dict[str, Any], preset: str | None) -> dict[str, Any]:
    if not preset:
        return config
    catalog = load_catalog()
    presets = catalog.get("load_presets") or {}
    p = presets.get(preset)
    if not p:
        return config
    cfg = dict(config)
    payloads = dict(cfg.get("payloads") or {})
    bench = dict(payloads.get("bench_run") or {})
    bench.update(p)
    if "iterations" in p:
        bench.pop("duration", None)
    elif "duration" in p:
        bench.pop("iterations", None)
    payloads["bench_run"] = bench
    cfg["payloads"] = payloads
    cfg["run_profile"] = "load"
    return cfg


def apply_run_profile(config: dict[str, Any], profile: str | None) -> dict[str, Any]:
    cfg = dict(config)
    prof = (profile or cfg.get("run_profile") or "load").lower()
    if prof not in ("debug", "load"):
        prof = "load"
    cfg["run_profile"] = prof
    payloads = dict(cfg.get("payloads") or {})
    bench = dict(payloads.get("bench_run") or {})
    if prof == "debug":
        bench["vus"] = 1
        bench["duration"] = "1s"
        bench["iterations"] = 1
    payloads["bench_run"] = bench
    cfg["payloads"] = payloads
    return cfg
