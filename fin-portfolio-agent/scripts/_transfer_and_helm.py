"""Transfer already-built am-fin-agent image into VPS kind + helm upgrade."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOST = "203.174.22.129"
KIND_CLUSTER = "am-preprod"
RELEASE = "am-fin-agent"
NAMESPACE = "am-apps-dev"
ROOT = Path(r"a:\InfraCode\AM-Portfolio-grp")
CHART = ROOT / "am-pipelines" / "helm" / "universal-chart"
VALUES_LOCAL = ROOT / "am-agents" / "fin-portfolio-agent" / "helm" / "values.dev.local.yaml"
KUBECONFIG = Path.home() / ".am" / "kubeconfig.vps"
TAG = Path(os.environ["TEMP"]) / "fin-agent-tag.txt"
IMAGE_TAG = TAG.read_text(encoding="utf-8").strip() if TAG.is_file() else "local-202608021117"
IMAGE = f"ghcr.io/am-portfolio/am-fin-agent:{IMAGE_TAG}"


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
    # Prefer keys written by probe script
    probe = Path(os.environ["TEMP"]) / "langfuse_keys.env"
    if probe.is_file():
        e = load_env(probe)
        if e.get("LANGFUSE_PUBLIC_KEY") and e.get("LANGFUSE_SECRET_KEY"):
            return e["LANGFUSE_PUBLIC_KEY"], e["LANGFUSE_SECRET_KEY"]
    vault = ROOT / "am-env-vault" / "environments" / "local" / "am-platform__secrets.env"
    env = load_env(vault)
    return env.get("LANGFUSE_PUBLIC_KEY", ""), env.get("LANGFUSE_SECRET_KEY", "")


def main() -> int:
    try:
        import paramiko
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "paramiko", "-q"])
        import paramiko

    infra = load_env(ROOT / "am-infra" / ".env.infra")
    vps = load_env(ROOT / "VPS" / ".env")
    user = infra.get("VPS_USER") or "root"
    password = infra.get("VPS_PASS") or vps.get("VPS_PASSWORD") or ""
    print(f"IMAGE={IMAGE} pass_len={len(password)}")

    # Verify image exists locally
    subprocess.check_call(["docker", "image", "inspect", IMAGE], stdout=subprocess.DEVNULL)

    with tempfile.TemporaryDirectory() as td:
        tar = Path(td) / "am-fin-agent.tar"
        print("=== docker save ===")
        subprocess.check_call(["docker", "save", "-o", str(tar), IMAGE])
        print(f"tar_mb={tar.stat().st_size / 1e6:.1f}")

        print("=== scp ===")
        transport = paramiko.Transport((HOST, 22))
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        assert sftp is not None
        remote = f"/tmp/am-fin-agent-{IMAGE_TAG}.tar"
        sftp.put(str(tar), remote)
        sftp.close()
        transport.close()

        print("=== kind load ===")
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
        for cmd in [
            f"kind load image-archive {remote} --name {KIND_CLUSTER}",
            f"rm -f {remote}",
        ]:
            print(f"$ {cmd}")
            _i, stdout, stderr = client.exec_command(cmd, timeout=900)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
            if out.strip():
                print(out[-1500:])
            if err.strip():
                print(err[-1500:])
            if code != 0:
                client.close()
                raise SystemExit(f"failed ({code}): {cmd}")
        client.close()

    pk, sk = langfuse_keys()
    print(f"langfuse_pk_len={len(pk)} sk_len={len(sk)}")
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
        f"global.image.tag={IMAGE_TAG}",
        "--kubeconfig",
        str(KUBECONFIG),
        "--wait",
        "--timeout",
        "5m",
    ]
    if pk and sk:
        helm += ["--set", f"env.LANGFUSE_PUBLIC_KEY={pk}", "--set", f"env.LANGFUSE_SECRET_KEY={sk}"]
    else:
        print("WARNING: no Langfuse keys; deploying with PROMPT_SOURCE still langfuse (file fallback)")
    env = os.environ.copy()
    env["KUBECONFIG"] = str(KUBECONFIG)
    print("=== helm upgrade ===")
    subprocess.check_call(helm, env=env)
    print(f"DEPLOYED {IMAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
