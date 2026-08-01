from __future__ import annotations

from app.schema.loader import SchemaCatalog
from app.prompts.builder import _operations_list, _catalog_snippet

REACT_SYSTEM_PROMPT = """You are an autonomous Tool Execution Agent operating in a loop.
Your task is to satisfy the user's request by calling tools and observing their outputs.

Available Tools:
{operations}

Tool Schemas:
{catalog}

Execution History:
{history}

Based on the user's request and the execution history, decide what to do next.
You must output exactly ONE of the following JSON structures (and nothing else):

Option 1 (Take an Action):
{{
  "action": {{
    "backend": "backend_name",
    "operation": "operation_name",
    "params": {{"key": "value"}}
  }}
}}

Option 2 (Provide Final Answer):
{{
  "answer": "The final result or observation that satisfies the user's request."
}}
"""

def build_react_prompt(
    history: str,
    catalog: SchemaCatalog | None = None,
    backends: list[str] | None = None,
) -> str:
    ops = _operations_list(backends)
    schemas = _catalog_snippet(catalog, backends) if catalog else "(no schemas loaded)"
    
    return REACT_SYSTEM_PROMPT.format(
        operations=ops,
        catalog=schemas,
        history=history,
    )
