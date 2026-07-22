"""Save local SPT image, upload to VPS, kind-load into cluster.

Requires env:
  SPT_VPS_HOST, SPT_VPS_USER, SPT_VPS_PASSWORD
Optional:
  SPT_VPS_IMAGE (default ghcr.io/am-portfolio/am-spt-poc:spt-dev)
  SPT_KIND_CLUSTER (default am-preprod)
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import paramiko

IMAGE = os.environ.get("SPT_VPS_IMAGE", "ghcr.io/am-portfolio/am-spt-poc:spt-dev")
KIND_CLUSTER = os.environ.get("SPT_KIND_CLUSTER", "am-preprod")
REMOTE_TAR = "/tmp/am-spt-poc-spt-dev.tar"


def _require_env(name: str) -> str:
    val = (os.environ.get(name) or "").strip()
    if not val:
        print(f"Missing required env: {name}", file=sys.stderr)
        sys.exit(1)
    return val


def run_local(cmd: list[str]) -> None:
    print(">>>", " ".join(cmd))
    subprocess.check_call(cmd)


def run_ssh(ssh: paramiko.SSHClient, cmd: str, timeout: int = 600) -> None:
    print(">>>", cmd)
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    stdout = out.read().decode()
    stderr = err.read().decode()
    if stdout:
        print(stdout[-3000:])
    if stderr and "DEPRECATED" not in stderr:
        print("ERR:", stderr[-1500:])
    rc = out.channel.recv_exit_status()
    print("exit", rc)
    if rc != 0:
        raise SystemExit(rc)


def main() -> None:
    host = _require_env("SPT_VPS_HOST")
    user = _require_env("SPT_VPS_USER")
    password = _require_env("SPT_VPS_PASSWORD")

    local_tar = os.path.join(tempfile.gettempdir(), "am-spt-poc-spt-dev.tar")
    run_local(["docker", "save", "-o", local_tar, IMAGE])
    print(f"saved {local_tar} ({os.path.getsize(local_tar) / (1024 * 1024):.1f} MiB)")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=password)
    sftp = ssh.open_sftp()
    print("Uploading image tar...")
    sftp.put(local_tar, REMOTE_TAR)
    sftp.close()

    run_ssh(ssh, f"docker load -i {REMOTE_TAR}")
    run_ssh(ssh, f"kind load docker-image {IMAGE} --name {KIND_CLUSTER}")
    ssh.close()
    print("Kind load done.")


if __name__ == "__main__":
    main()
