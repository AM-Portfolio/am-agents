from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

import yaml

from app.config import TOOLS_DIR
from tools._protocol import IntegrationTool, PromptRef, ToolManifest

logger = logging.getLogger(__name__)

SKIP_DIRS = {"_template", "_shared", "__pycache__"}


def _parse_prompt_ref(raw: dict[str, Any] | None) -> PromptRef | None:
    if not raw:
        return None
    return PromptRef(
        source=str(raw.get("source") or "file"),
        name=str(raw.get("name") or ""),
        label=str(raw.get("label") or "{{APP_ENV}}"),
        fallback=str(raw.get("fallback") or "prompts/intent.yaml"),
        optional=bool(raw.get("optional", False)),
    )


def load_manifest(path: Path) -> ToolManifest:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    prompts_raw = raw.get("prompts") or {}
    prompts: dict[str, PromptRef] = {}
    for key, value in prompts_raw.items():
        ref = _parse_prompt_ref(value if isinstance(value, dict) else None)
        if ref:
            prompts[key] = ref
    vault = raw.get("vault") or {}
    return ToolManifest(
        name=str(raw.get("name") or path.parent.name),
        display_name=str(raw.get("display_name") or raw.get("name") or path.parent.name),
        enabled=bool(raw.get("enabled", True)),
        version=str(raw.get("version") or "1.0.0"),
        infer_keywords=list(raw.get("infer_keywords") or []),
        vault_path_template=vault.get("path_template"),
        env_prefix=str(raw.get("env_prefix") or ""),
        supports_mcp=bool(raw.get("supports_mcp", False)),
        mcp_server=raw.get("mcp_server"),
        has_entities=bool(raw.get("has_entities", False)),
        health_check=str(raw.get("health_check") or "skip"),
        prompts=prompts,
    )


def _import_plugin(tool_dir: Path) -> IntegrationTool | None:
    plugin_path = tool_dir / "plugin.py"
    if not plugin_path.exists():
        return None
    module_name = f"tools_{tool_dir.name}_plugin"
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "get_tool", None)
    if not callable(factory):
        logger.warning("plugin %s missing get_tool()", plugin_path)
        return None
    tool = factory()
    if not isinstance(tool, IntegrationTool):
        logger.warning("plugin %s get_tool() did not return IntegrationTool", plugin_path)
        return None
    return tool


def discover_tools(*, reload: bool = False) -> list[IntegrationTool]:
    if reload:
        clear_tool_cache()
    tools: list[IntegrationTool] = []
    if not TOOLS_DIR.exists():
        return tools
    for child in sorted(TOOLS_DIR.iterdir()):
        if not child.is_dir() or child.name in SKIP_DIRS or child.name.startswith("."):
            continue
        manifest_path = child / "manifest.yaml"
        if not manifest_path.exists():
            continue
        try:
            tool = _import_plugin(child)
            if tool:
                tools.append(tool)
        except Exception as exc:
            logger.exception("failed to load tool %s: %s", child.name, exc)
    return tools


_cache: list[IntegrationTool] | None = None


def get_tools(*, reload: bool = False) -> list[IntegrationTool]:
    global _cache
    if reload or _cache is None:
        _cache = discover_tools()
    return _cache


def get_enabled_tools(*, reload: bool = False) -> list[IntegrationTool]:
    return [t for t in get_tools(reload=reload) if t.is_enabled()]


def get_tool(name: str) -> IntegrationTool | None:
    for tool in get_enabled_tools():
        if tool.name == name:
            return tool
    return None


def clear_tool_cache() -> None:
    global _cache
    _cache = None


def merged_registry() -> dict[str, Any]:
    backends: dict[str, Any] = {}
    for tool in get_enabled_tools():
        entry = tool.registry_entry()
        if entry:
            backends[tool.name] = entry
    return {"backends": backends}


def infer_backends_from_query(query: str) -> list[str]:
    q = query.lower()
    scored: list[tuple[int, str]] = []
    for tool in get_enabled_tools():
        score = sum(1 for kw in tool.infer_keywords() if kw.lower() in q)
        if score:
            scored.append((score, tool.name))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [name for _, name in scored]
