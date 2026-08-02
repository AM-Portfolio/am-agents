"""Save+SCP+kind-load am-fin-agent image. Usage: python _kind_load_only.py <image>"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import paramiko

ROOT = Path(r"a:\InfraCode\AM-Portfolio-grp")
HOST = "203.174.22.129"
KIND = "am-preprod"


def load_env(path: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    if not path.is_file():
        return d
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: _kind_load_only.py <image>", file=sys.stderr)
        return 2
    image = sys.argv[1]
    tag = image.rsplit(":", 1)[-1]
    infra = load_env(ROOT / "am-infra" / ".env.infra")
    vps = load_env(ROOT / "VPS" / ".env")
    user = infra.get("VPS_USER") or "root"
    password = infra.get("VPS_PASS") or vps.get("VPS_PASSWORD") or ""
    print(f"image={image} user={user} pass_len={len(password)}")
    if not password:
        print("missing VPS password", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as td:
        tar = Path(td) / "img.tar"
        subprocess.check_call(["docker", "save", "-o", str(tar), image])
        print(f"tar_mb={tar.stat().st_size / 1e6:.1f}")
        transport = paramiko.Transport((HOST, 22))
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        remote = f"/tmp/{tag}.tar"
        sftp.put(str(tar), remote)
        sftp.close()
        transport.close()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        username=user,
        password=password,
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    cmd = f"kind load image-archive {remote} --name {KIND} && rm -f {remote}"
    print(f"$ {cmd}")
    _i, stdout, stderr = client.exec_command(cmd, timeout=900)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    if out.strip():
        print(out[-1000:])
    if err.strip():
        print(err[-1000:])
    print(f"exit={code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
