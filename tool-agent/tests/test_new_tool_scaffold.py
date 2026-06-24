import shutil
import subprocess
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]


def test_new_tool_scaffold(tmp_path: Path):
    name = "scaffold_demo"
    target = AGENT_ROOT / "tools" / name
    if target.exists():
        shutil.rmtree(target)

    proc = subprocess.run(
        [sys.executable, "scripts/new_tool.py", name, "--keywords", "demo,test", "--display-name", "Demo"],
        cwd=AGENT_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout

    try:
        assert (target / "plugin.py").exists()
        assert (target / "manifest.yaml").exists()
        val = subprocess.run(
            [sys.executable, "scripts/validate_tool.py", name],
            cwd=AGENT_ROOT,
            capture_output=True,
            text=True,
        )
        assert val.returncode == 0, val.stderr + val.stdout
    finally:
        if target.exists():
            shutil.rmtree(target)
        tools_md = AGENT_ROOT / "docs" / "TOOLS.md"
        if tools_md.exists():
            text = tools_md.read_text(encoding="utf-8")
            tools_md.write_text(text.replace(f"- [Demo](tools/{name}/README.md) — `{name}`\n", ""), encoding="utf-8")
