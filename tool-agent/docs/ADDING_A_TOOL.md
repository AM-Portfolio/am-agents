# Adding a tool integration

1. `python scripts/new_tool.py <name> --keywords ... [--has-entities] [--enable]`
2. Fill `registry.yaml` operations
3. Implement `adapter.py`
4. Add `search/parse_rules.py` and `search/resolve.py`
5. Add `prompts/intent.yaml` (+ optional `examples.yaml`)
6. Add `schema/{env}.yaml` if using entities
7. `pytest tools/<name>/tests`
8. `python scripts/validate_tool.py <name>`
9. PR — only touch `tools/<name>/`, config, helm values

Core files (`app/graph.py`, `tools/_loader.py`) should not need changes.
