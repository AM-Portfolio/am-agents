from __future__ import annotations


def normalize_vault_path(path: str) -> str:
    """Normalize user/schema paths to vault-mcp-server KV path under mount `apps`."""
    p = path.strip().strip("/")
    if p.startswith("apps/data/"):
        return p[len("apps/data/") :]
    if p.startswith("apps/"):
        return p[len("apps/") :]
    if p.startswith("data/preprod/"):
        return p[len("data/") :]
    if p.startswith("data/dev/"):
        return p[len("data/") :]
    return p
