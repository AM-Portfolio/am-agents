"""Build am-fin-agent, SSH-transfer into VPS kind, helm upgrade am-apps-dev."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HOST = "203.174.22.129"
KIND_CLUSTER = "am-preprod"
RELEASE = "am-fin-agent"
NAMESPACE = "am-apps-dev"
ROOT = Path(r"a:\InfraCode\AM-Portfolio-grp")
AGENTS = ROOT / "am-agents"
CHART = ROOT / "am-pipelines" / "helm" / "universal-chart"
VALUES_LOCAL = AGENTS / "fin-portfolio-agent" / "helm" / "values.dev.local.yaml"
KUBECONFIG = Path.home() / ".am" / "kubeconfig.vps"
TAG = "local-" + datetime.now().strftime("%Y%m%d%H%M")
IMAGE = f"ghcr.io/am-portfolio/am-fin-agent:{TAG}"


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


def langfuse_keys() -> tuple[str, str]:
    vault = ROOT / "am-env-vault" / "environments" / "local" / "am-platform__secrets.env"
    env = load_env(vault)
    pk = env.get("LANGFUSE_PUBLIC_KEY", "")
    sk = env.get("LANGFUSE_SECRET_KEY", "")
    if not pk or not sk:
        raise SystemExit("LANGFUSE keys missing in am-env-vault")
    return pk, sk


def ensure_paramiko():
    try:
        import paramiko  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "paramiko", "-q"])
        import paramiko  # noqa: F401


def main() -> int:
    ensure_paramiko()
    import paramiko

    infra = load_env(ROOT / "am-infra" / ".env.infra")
    vps = load_env(ROOT / "VPS" / ".env")
    user = infra.get("VPS_USER") or "root"
    password = infra.get("VPS_PASS") or vps.get("VPS_PASSWORD") or ""
    print(f"IMAGE={IMAGE}")
    print(f"SSH host={HOST} user={user} pass_len={len(password)}")

    # 1) Build
    print("=== docker build ===")
    subprocess.check_call(
        [
            "docker",
            "build",
            "-f",
            str(AGENTS / "fin-portfolio-agent" / "Dockerfile"),
            "-t",
            IMAGE,
            str(AGENTS),
        ]
    )

    # 2) Save + SCP + kind load
    with tempfile.TemporaryDirectory() as td:
        tar = Path(td) / "am-fin-agent.tar"
        print("=== docker save ===")
        subprocess.check_call(["docker", "save", "-o", str(tar), IMAGE])
        print(f"tar_mb={tar.stat().st_size / 1e6:.1f}")

        print("=== scp + kind load ===")
        transport = paramiko.Transport((HOST, 22))
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        remote = f"/tmp/am-fin-agent-{TAG}.tar"
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
        cmds = [
            f"kind load image-archive {remote} --name {KIND_CLUSTER}",
            f"rm -f {remote}",
            f"docker images {IMAGE} || true",
        ]
        for cmd in cmds:
            print(f"$ {cmd}")
            _stdin, stdout, stderr = client.exec_command(cmd, timeout=600)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
            if out.strip():
                print(out[-2000:])
            if err.strip():
                print(err[-2000:])
            if code != 0:
                client.close()
                raise SystemExit(f"remote cmd failed ({code}): {cmd}")
        client.close()

    # 3) Helm upgrade (local kubeconfig)
    pk, sk = langfuse_keys()
    print("=== helm upgrade ===")
    helm = [
        "helm",
        "upgrade",
        "--install",
        RELEASE,
        str(CHART),
        "-n",
        NAMESPACE,
        "-f",
        str(VALUES_LOCAL),
        "--set",
        f"global.image.tag={TAG}",
        "--set",
        f"env.LANGFUSE_PUBLIC_KEY={pk}",
        "--set",
        f"env.LANGFUSE_SECRET_KEY={sk}",
        "--kubeconfig",
        str(KUBECONFIG),
        "--wait",
        "--timeout",
        "5m",
    ]
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["KUBECONFIG"] = str(KUBECONFIG)
    subprocess.check_call(helm, env=env)
    print(f"DEPLOYED {IMAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
