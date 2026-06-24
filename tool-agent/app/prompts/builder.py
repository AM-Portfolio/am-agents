from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.prompts.provider import compile_prompt, get_prompt_provider
from app.schema.loader import SchemaCatalog
from tools._loader import get_enabled_tools, infer_backends_from_query, merged_registry


def _operations_list(backends: list[str] | None = None) -> str:
    registry = merged_registry().get("backends") or {}
    lines: list[str] = []
    for name, cfg in sorted(registry.items()):
        if backends and name not in backends:
            continue
        ops = sorted((cfg.get("operations") or {}).keys())
        if ops:
            lines.append(f"- {name}: {', '.join(ops)}")
    return "\n".join(lines) or "(no tools enabled)"


def _resolve_label(label_template: str) -> str:
    return label_template.replace("{{APP_ENV}}", settings.langfuse_prompt_label())


def build_intent_prompt(
    query: str,
    backend_hint: str | None,
    *,
    catalog: SchemaCatalog | None = None,
) -> str:
    provider = get_prompt_provider()
    catalog = catalog or SchemaCatalog()
    candidates = [backend_hint] if backend_hint else infer_backends_from_query(query)
    candidates = [c for c in candidates if c][:2]

    base = provider.get(
        "tool-agent/intent/base",
        label=settings.langfuse_prompt_label(),
        fallback_path=Path(__file__).resolve().parent / "base.yaml",
    )
    snippets: list[str] = []
    enabled = {t.name: t for t in get_enabled_tools()}
    for backend in candidates:
        tool = enabled.get(backend)
        if not tool:
            continue
        ref = tool.manifest.prompts.get("intent")
        if not ref:
            continue
        fallback = tool.tool_dir / ref.fallback
        snippet = provider.get(ref.name or f"tool-agent/intent/{backend}", label=_resolve_label(ref.label), fallback_path=fallback)
        if snippet.content:
            snippets.append(snippet.content)
        examples_ref = tool.manifest.prompts.get("examples")
        if examples_ref and not examples_ref.optional:
            ex = provider.get(
                examples_ref.name or f"tool-agent/intent/{backend}/examples",
                label=_resolve_label(examples_ref.label),
                fallback_path=tool.tool_dir / examples_ref.fallback,
            )
            if ex.content:
                snippets.append(ex.content)

    variables = {
        "operations_list": _operations_list(candidates or None),
        "catalog_snippet": catalog.snippet(backends=candidates or None),
        "query": query,
    }
    body = compile_prompt(base.content, variables)
    if snippets:
        body = body + "\n\n" + "\n\n".join(snippets)
    return body
