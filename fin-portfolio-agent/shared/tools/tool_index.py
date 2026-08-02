"""
tool_index.py
=============
ChromaDB-backed vector index for dynamic tool retrieval.

Why this exists:
  With 100–600+ tools registered from multiple micro-service OpenAPI specs,
  passing ALL of them to the LLM on every request wastes tokens and degrades
  quality. This module embeds every tool description at startup and, at query
  time, retrieves only the top-k most semantically relevant tools.

Shared by:
  - FinanceAgent (ReAct loop) via agent_node()
  - MCP server via call_tool()

Usage:
    from tools.tool_index import index_all_tools, retrieve_tools

    # At startup, after register_openapi_tools():
    index_all_tools()

    # At request time:
    relevant = retrieve_tools("get portfolio summary", top_k=8)
    # → list of tool-schema dicts to pass to the LLM
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Lazy-import heavy dependencies so startup doesn't fail if not installed ─

_chroma_client = None
_collection = None
_embed_model = None
_cross_encoder = None


def _init():
    """Initialise ChromaDB and the sentence-transformer model (once)."""
    global _chroma_client, _collection, _embed_model, _cross_encoder

    if _collection is not None:
        return  # already initialised

    try:
        import chromadb
        from sentence_transformers import SentenceTransformer, CrossEncoder

        _chroma_client = chromadb.Client()  # embedded, no separate server
        _collection = _chroma_client.get_or_create_collection(
            name="tools",
            metadata={"hnsw:space": "cosine"},  # cosine similarity
        )
        # Small, fast model – good balance of speed vs quality
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        
        # Load a cross-encoder for re-ranking (optional but powerful)
        try:
            _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("ToolIndex: CrossEncoder loaded for re-ranking.")
        except Exception as e:
            logger.warning(f"ToolIndex: Could not load CrossEncoder ({e}). Skipping re-ranking.")

        logger.info("ToolIndex: ChromaDB collection and embedding model initialised.")

    except ImportError as exc:
        logger.warning(
            "ToolIndex: could not import chromadb / sentence-transformers (%s). "
            "Falling back to full TOOL_REGISTRY (no retrieval). "
            "Install with: pip install chromadb sentence-transformers",
            exc,
        )


# ─── Public API ───────────────────────────────────────────────────────────────


def index_all_tools() -> int:
    """
    Embed all tools currently in TOOL_REGISTRY and upsert them into ChromaDB.

    Should be called once at startup, AFTER register_openapi_tools() has run.

    Returns:
        Number of tools indexed.
    """
    _init()

    from shared.tools.registry import TOOL_REGISTRY  # avoid circular import

    if _collection is None:
        logger.warning("ToolIndex: ChromaDB not available – skipping indexing.")
        return 0

    docs, ids, metadatas = [], [], []

    for tool in TOOL_REGISTRY:
        if tool.get("type") != "function":
            continue
        fn = tool["function"]
        name: str = fn["name"]
        description: str = fn.get("description", name)
        
        # Pull path from _meta if available (OpenAPI tools)
        meta = tool.get("_meta", {})
        path = meta.get("path", "")
        
        # Build a richer text for embedding: name + path + description + param names
        param_names = ", ".join(fn.get("parameters", {}).get("properties", {}).keys())
        embed_text = f"{name}: {path} {description}. params: {param_names}"

        docs.append(embed_text)
        ids.append(name)
        metadatas.append({"name": name, "path": path, "description": description})

    if not docs:
        logger.warning("ToolIndex: no tools to index.")
        return 0

    embeddings = _embed_model.encode(docs, show_progress_bar=False).tolist()
    _collection.upsert(documents=docs, embeddings=embeddings, ids=ids, metadatas=metadatas)

    logger.info("ToolIndex: indexed %d tools into ChromaDB.", len(docs))
    return len(docs)


def keyword_search(query: str, top_k: int = 10) -> List[str]:
    """
    Performs a lexical (keyword) search on tool names and paths.
    Returns a list of tool names (IDs).
    """
    from shared.tools.registry import TOOL_REGISTRY, OPENAPI_EXECUTOR_MAP
    
    query = query.lower()
    scores = []
    
    for tool in TOOL_REGISTRY:
        if tool.get("type") != "function":
            continue
        fn = tool["function"]
        name = fn["name"]
        description = fn.get("description", "").lower()
        
        # Pull path from the executor map, not the schema!
        meta = OPENAPI_EXECUTOR_MAP.get(name, {})
        path = meta.get("path", "").lower()
        name_lower = name.lower()
        
        score = 0
        # Direct path match (highest priority)
        if query in path and path:
            score += 10
        # Name match
        if query in name_lower:
            score += 8
        # Partial keyword overlaps
        keywords = query.split()
        for kw in keywords:
            if kw in name_lower: score += 2
            if kw in path: score += 3
            if kw in description: score += 1
            
        if score > 0:
            scores.append((name, score))
            
    # Sort by score descending
    scores.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in scores[:top_k]]


def retrieve_tools(query: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """
    Hybrid search: Vector + Lexical + Re-ranking.
    """
    from shared.tools.registry import TOOL_REGISTRY  # avoid circular import

    _init()

    if _collection is None or _embed_model is None:
        logger.warning("ToolIndex: returning all tools (ChromaDB unavailable).")
        return [_strip_meta(t) for t in TOOL_REGISTRY if t.get("type") == "function"]

    try:
        # 1. Semantic candidates
        query_embedding = _embed_model.encode([query], show_progress_bar=False).tolist()
        v_results = _collection.query(
            query_embeddings=query_embedding,
            n_results=min(20, _collection.count()),
        )
        vector_names = [m["name"] for m in v_results["metadatas"][0]]
        
        # 2. Keyword candidates
        keyword_names = keyword_search(query, top_k=20)
        
        # 3. Merge candidates (Union)
        candidate_names = list(set(vector_names + keyword_names))
        candidates = [
            t for t in TOOL_REGISTRY 
            if t.get("function", {}).get("name") in candidate_names
        ]
        
        # 4. Re-ranking with Cross-Encoder (if available)
        if _cross_encoder and candidates and query:
            rank_pairs = []
            for t in candidates:
                fn = t["function"]
                meta = t.get("_meta", {})
                tool_text = f"{fn['name']} {meta.get('path', '')} {fn.get('description', '')}"
                rank_pairs.append((query, tool_text))
            
            scores = _cross_encoder.predict(rank_pairs)
            # Combine back with tool names and sort
            scored_candidates = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
            candidates = [c[0] for c in scored_candidates]
        
        # Return top_k
        return [_strip_meta(t) for t in candidates[:top_k]]

    except Exception as exc:
        logger.error("ToolIndex: query failed (%s) – returning basic match.", exc)
        return [_strip_meta(t) for t in TOOL_REGISTRY if t.get("type") == "function"][:top_k]


def reindex_tool(tool_schema: Dict[str, Any]) -> None:
    """
    Add or update a single tool in the ChromaDB index.
    """
    _init()
    if _collection is None or _embed_model is None:
        return

    fn = tool_schema.get("function", {})
    name = fn.get("name", "")
    if not name:
        return

    description = fn.get("description", name)
    meta = tool_schema.get("_meta", {})
    path = meta.get("path", "")
    param_names = ", ".join(fn.get("parameters", {}).get("properties", {}).keys())
    embed_text = f"{name}: {path} {description}. params: {param_names}"

    embedding = _embed_model.encode([embed_text], show_progress_bar=False).tolist()
    _collection.upsert(documents=[embed_text], embeddings=embedding,
                       ids=[name], metadatas=[{"name": name, "path": path, "description": description}])
    logger.debug("ToolIndex: re-indexed tool %s.", name)


# ─── Internal Helpers ─────────────────────────────────────────────────────────


def _strip_meta(tool: Dict) -> Dict:
    """Return a copy of the tool schema without the private '_meta' key."""
    return {k: v for k, v in tool.items() if k != "_meta"}


def tool_count() -> Optional[int]:
    """Return the number of tools currently indexed, or None if unavailable."""
    if _collection is None:
        return None
    try:
        return _collection.count()
    except Exception:
        return None
