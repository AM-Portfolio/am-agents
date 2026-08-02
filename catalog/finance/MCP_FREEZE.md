# Freeze notice — am-mcp-server (Java)

Tool SoT is Java `am-mcp-server` (`list_tools`). Fin-agent discovers and caches
schemas at runtime; do not reintroduce a static `tools.yaml` catalog for chat.

When adding a tool:
1. Implement in am-mcp-server
2. Add `artifactType` mapping in fin-agent `artifact_resolver.py` if the UI needs a typed artifact
3. Flutter registers the widget for that `artifactType` (separate change)

Do not add hand-written portfolio data tools back onto the fin-agent chat path.
