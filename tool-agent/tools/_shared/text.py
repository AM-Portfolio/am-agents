from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.config import AGENT_ROOT


def render_template(text: str, variables: dict[str, str]) -> str:
    out = text
    for key, value in variables.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    return out


def load_yaml_text(path: Path) -> str:
    if not path.exists():
        return ""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        if "content" in data:
            return str(data["content"]).strip()
        if "prompt" in data:
            return str(data["prompt"]).strip()
    return path.read_text(encoding="utf-8").strip()
