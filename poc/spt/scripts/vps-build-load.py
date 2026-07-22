"""Build am-spt-poc image on VPS (offline) and load into kind.

Requires env:
  SPT_VPS_HOST, SPT_VPS_USER, SPT_VPS_PASSWORD
Optional:
  SPT_VPS_IMAGE (default ghcr.io/am-portfolio/am-spt-poc:spt-dev)
  SPT_KIND_CLUSTER (default am-preprod)
"""
import os
import sys
import paramiko

IMAGE = os.environ.get("SPT_VPS_IMAGE", "ghcr.io/am-portfolio/am-spt-poc:spt-dev")
KIND_CLUSTER = os.environ.get("SPT_KIND_CLUSTER", "am-preprod")


def _require_env(name: str) -> str:
    val = (os.environ.get(name) or "").strip()
    if not val:
        print(f"Missing required env: {name}", file=sys.stderr)
        sys.exit(1)
    return val


def run(ssh, cmd, timeout=600):
    print(">>>", cmd)
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    stdout = out.read().decode()
    stderr = err.read().decode()
    if stdout:
        print(stdout[-5000:])
    if stderr and "DEPRECATED" not in stderr:
        print("ERR:", stderr[-1500:])
    rc = out.channel.recv_exit_status()
    print("exit", rc)
    return rc


def main():
    host = _require_env("SPT_VPS_HOST")
    user = _require_env("SPT_VPS_USER")
    password = _require_env("SPT_VPS_PASSWORD")

    tar = os.path.join(os.environ.get("TEMP", "/tmp"), "am-spt-poc-build.tar.gz")
    if not os.path.isfile(tar):
        print(f"Missing tarball: {tar}", file=sys.stderr)
        sys.exit(1)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=password)

    sftp = ssh.open_sftp()
    print("Uploading tarball...")
    sftp.put(tar, "/tmp/am-spt-build/am-spt-poc-build.tar.gz")
    sftp.close()

    steps = [
        "mkdir -p /tmp/am-spt-build",
        "cd /tmp/am-spt-build && rm -rf spt && tar -xzf am-spt-poc-build.tar.gz",
        f"cd /tmp/am-spt-build/spt && docker build --no-cache -t {IMAGE} .",
        f"kind load docker-image {IMAGE} --name {KIND_CLUSTER}",
        f"docker images {IMAGE}",
    ]
    for cmd in steps:
        if run(ssh, cmd) != 0:
            ssh.close()
            sys.exit(1)

    ssh.close()
    print("Done.")


if __name__ == "__main__":
    main()
