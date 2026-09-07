"""Merge AM_FIN_AGENT_CLIENT_SECRET into prod am-agents Vault path. Never prints secrets."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

CREDS = pathlib.Path.home() / ".asrax" / "credentials.env"
REALM = "am-realm"
CLIENT_UUID = "341d001b-0b4c-4aab-81e8-21369bed15c7"
VAULT_CANDIDATES = (
    "apps/prod/services/am-agents",
    "apps/data/prod/services/am-agents",
    "secret/prod/services/am-agents",
)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def load_creds() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in CREDS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def http_form(url: str, data: dict[str, str], headers: dict[str, str] | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": UA,
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def http_json(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def vault_get(path: str) -> dict | None:
    try:
        raw = subprocess.check_output(
            ["vault", "kv", "get", "-format=json", path],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        return None
    payload = json.loads(raw)
    return payload.get("data", {}).get("data") or {}


def vault_put(path: str, data: dict) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        tmp = f.name
    try:
        subprocess.check_call(["vault", "kv", "put", path, f"@{tmp}"])
    finally:
        pathlib.Path(tmp).unlink(missing_ok=True)


def main() -> None:
    creds = load_creds()
    for req in ("VAULT_ADDR", "VAULT_TOKEN", "KEYCLOAK_URL", "KEYCLOAK_ADMIN", "KEYCLOAK_ADMIN_PASSWORD"):
        if not creds.get(req):
            raise SystemExit(f"missing {req} in credentials.env")
    os.environ["VAULT_ADDR"] = creds["VAULT_ADDR"]
    os.environ["VAULT_TOKEN"] = creds["VAULT_TOKEN"]

    kc = creds["KEYCLOAK_URL"].rstrip("/")
    token = http_form(
        f"{kc}/realms/master/protocol/openid-connect/token",
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": creds["KEYCLOAK_ADMIN"],
            "password": creds["KEYCLOAK_ADMIN_PASSWORD"],
        },
    )["access_token"]
    secret = http_json(
        f"{kc}/admin/realms/{REALM}/clients/{CLIENT_UUID}/client-secret",
        token,
    ).get("value")
    if not secret:
        raise SystemExit("empty Keycloak client secret")
    print("ok keycloak secret retrieved (not printed)")

    probed: list[tuple[str, dict]] = []
    for path in VAULT_CANDIDATES:
        data = vault_get(path)
        if data is None:
            print(f"miss {path}")
            continue
        names = ",".join(sorted(data))
        print(f"hit {path} nkeys={len(data)} names={names}")
        probed.append((path, data))

    preferred = None
    for path, data in probed:
        if "LITELLM_MASTER_KEY" in data or "TOGETHER_API_KEY" in data or len(data) > 2:
            preferred = (path, data)
            break
    if preferred is None and probed:
        preferred = max(probed, key=lambda item: len(item[1]))
    if preferred is None:
        target, existing = VAULT_CANDIDATES[0], {}
        print(f"ok vault path missing, will create {target}")
    else:
        target, existing = preferred
        print(f"ok merge target {target} keys={len(existing)}")

    existing["AM_FIN_AGENT_CLIENT_ID"] = "am-fin-agent-service"
    existing["AM_FIN_AGENT_CLIENT_SECRET"] = secret
    vault_put(target, existing)
    print(f"ok patched {target} (AM_FIN_AGENT_CLIENT_ID + SECRET; {len(existing)} keys total)")
    print("ok secret length", len(secret))


if __name__ == "__main__":
    main()
