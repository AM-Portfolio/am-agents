from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.prompts.provider import compile_prompt, get_prompt_provider
from app.schema.loader import SchemaCatalog
from tools._loader import get_enabled_tools, get_tool, infer_backends_from_query


def _operations_list(backends: list[str] | None = None) -> str:
    from tools._loader import merged_registry

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


def _catalog_snippet(catalog: SchemaCatalog, backends: list[str] | None) -> str:
    parts = [catalog.snippet(backends=backends)]
    if not backends or "vault" in backends:
        try:
            from tools.vault.path_cache import snippet as vault_snippet

            parts.append(vault_snippet())
        except Exception:
            pass
    if not backends or "kafka" in backends:
        try:
            from tools.kafka.topic_cache import snippet as kafka_snippet

            parts.append(kafka_snippet())
        except Exception:
            pass
    return "\n".join(p for p in parts if p)


def build_intent_prompt(
    query: str,
    backend_hint: str | None,
    *,
    catalog: SchemaCatalog | None = None,
    god_mode: bool = False,
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
        if god_mode:
            god_ref = tool.manifest.prompts.get("god_mode")
            if god_ref:
                god = provider.get(
                    god_ref.name or f"tool-agent/intent/{backend}/god_mode",
                    label=_resolve_label(god_ref.label),
                    fallback_path=tool.tool_dir / god_ref.fallback,
                )
                if god.content:
                    snippets.append(god.content)

    variables = {
        "operations_list": _operations_list(candidates or None),
        "catalog_snippet": _catalog_snippet(catalog, candidates or None),
        "query": query,
    }
    body = compile_prompt(base.content, variables)
    if snippets:
        body = body + "\n\n" + "\n\n".join(snippets)
    if god_mode:
        body = body + "\n\nGOD MODE is ON — prioritize observability LogQL and high-confidence params."
    return body


def build_summary_prompt(
    *,
    backend: str,
    operation: str,
    query: str,
    data_preview: str,
    god_mode: bool = False,
) -> tuple[str, str]:
    provider = get_prompt_provider()
    tool = get_tool(backend)
    system = "You summarize infra tool query results briefly in plain English."
    if tool:
        analysis_ref = tool.manifest.prompts.get("analysis")
        if analysis_ref:
            analysis = provider.get(
                analysis_ref.name or f"tool-agent/analysis/{backend}",
                label=_resolve_label(analysis_ref.label),
                fallback_path=tool.tool_dir / analysis_ref.fallback,
            )
            if analysis.content:
                system = analysis.content.strip()
    if god_mode:
        system = system + "\n\nGOD MODE: provide full SRE incident analysis, not a one-line summary."
    user = (
        f"Original question: {query}\n"
        f"Executed: {backend}.{operation}\n"
        f"Data preview:\n{data_preview}"
    )
    return system, user
