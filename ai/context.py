"""Context packing for AI prompts with token-aware selection."""

import os
from pathlib import Path
from typing import Dict, List, Optional, NamedTuple

from ai.tools import repo_search, read_file


class ContextBundle(NamedTuple):
    """Context bundle with metadata."""
    context: str
    tokens_used: int
    sources: Dict[str, int]  # source -> count
    truncation_ratio: float


def estimate_tokens(text: str) -> int:
    """
    Rough token estimation (4 chars ≈ 1 token fallback).

    Args:
        text: Text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    # Rough estimation: ~4 characters per token for code
    return len(text) // 4


def gather_context(
    target_paths: List[str],
    selection: Optional[str],
    extra_queries: Optional[List[str]],
    max_tokens: int
) -> Dict:
    """
    Gather context for AI prompt within token budget.

    Strategy:
    1. Always include the selection (or active buffer up to 400 lines).
    2. Use symbol-adjacent snippets if queries provided.
    3. Use repo_search to fetch up to N nearby files; include top K snippets.
    4. Truncate to max_tokens margin (leave 20% budget for model output).

    Args:
        target_paths: Primary files to include.
        selection: Selected text (highest priority).
        extra_queries: Additional search queries for context.
        max_tokens: Maximum input tokens.

    Returns:
        Dict with 'context' (str) and 'tokens_used' (int).
    """
    context_parts = []
    tokens_used = 0
    output_margin = int(max_tokens * 0.2)  # Reserve 20% for output
    available_tokens = max_tokens - output_margin

    # 1. Include selection or target files
    if selection:
        selection_tokens = estimate_tokens(selection)
        if tokens_used + selection_tokens <= available_tokens:
            context_parts.append(f"Selected code:\n{selection}")
            tokens_used += selection_tokens
    else:
        # Include target files (up to 400 lines each)
        for path in target_paths[:3]:  # Limit to 3 primary files
            try:
                content = read_file(path, max_bytes=200_000)
                if content.startswith("Error:"):
                    continue
                lines = content.splitlines()
                if len(lines) > 400:
                    content = "\n".join(lines[:400]) + "\n... (truncated)"
                file_tokens = estimate_tokens(content)
                if tokens_used + file_tokens <= available_tokens:
                    context_parts.append(f"File: {path}\n{content}")
                    tokens_used += file_tokens
            except Exception:
                continue

    # 2. Add symbol-adjacent snippets
    if extra_queries:
        for query in extra_queries[:2]:  # Limit queries
            symbol_context = gather_symbol_adjacent_snippets(target_paths, query, available_tokens - tokens_used)
            if symbol_context["tokens_used"] > 0:
                context_parts.append(symbol_context["context"])
                tokens_used += symbol_context["tokens_used"]
                if tokens_used >= available_tokens:
                    break

    # 3. Add context from repo search if still space
    if extra_queries and tokens_used < available_tokens:
        for query in extra_queries[:3]:  # Limit queries
            try:
                results = repo_search(query, limit=3)
                for path, score in results:
                    if tokens_used >= available_tokens:
                        break
                    try:
                        content = read_file(path, max_bytes=50_000)  # Smaller for context files
                        if content.startswith("Error:"):
                            continue
                        # Take first/last 60 lines or around symbol hits
                        lines = content.splitlines()
                        if len(lines) > 120:
                            # First 60 + last 60
                            content = "\n".join(lines[:60] + ["..."] + lines[-60:])
                        file_tokens = estimate_tokens(content)
                        if tokens_used + file_tokens <= available_tokens:
                            context_parts.append(f"Related file: {path}\n{content}")
                            tokens_used += file_tokens
                    except Exception:
                        continue
            except Exception:
                continue

    return {
        "context": "\n\n".join(context_parts),
        "tokens_used": tokens_used
    }


def gather_symbol_adjacent_snippets(targets: List[str], symbols_query: str, budget_tokens: int) -> Dict:
    """
    Gather context snippets around symbol locations.

    Args:
        targets: Target file paths.
        symbols_query: Query to find relevant symbols.
        budget_tokens: Maximum tokens to use.

    Returns:
        Dict with 'context' and 'tokens_used'.
    """
    from pathlib import Path
    from indexer import build_or_load_symbols, query_symbols

    project_root = Path.cwd()
    index = build_or_load_symbols(project_root)

    # Query symbols
    symbols = query_symbols(index, symbols_query)

    context_parts = []
    tokens_used = 0
    output_margin = int(budget_tokens * 0.2)
    available_tokens = budget_tokens - output_margin

    # For each matching symbol, get adjacent code
    for symbol in symbols:
        if tokens_used >= available_tokens:
            break

        try:
            content = read_file(symbol.path, max_bytes=100_000)
            if content.startswith("Error:"):
                continue

            lines = content.splitlines()
            # Get lines around the symbol (e.g., 5 lines before and after)
            start = max(0, symbol.start_line - 6)  # 0-indexed
            end = min(len(lines), symbol.end_line + 4)

            snippet = "\n".join(lines[start:end])
            snippet_tokens = estimate_tokens(snippet)

            if tokens_used + snippet_tokens <= available_tokens:
                context_parts.append(f"Symbol: {symbol.name} ({symbol.kind}) in {symbol.path}\n{snippet}")
                tokens_used += snippet_tokens
        except Exception:
            continue

    return {
        "context": "\n\n".join(context_parts),
        "tokens_used": tokens_used
    }


def gather_context_v2(
    target_paths: List[str],
    selection: Optional[str],
    symbol_query: Optional[str],
    user_query: Optional[str],
    budget_tokens: int,
    weights: Optional[Dict[str, float]] = None
) -> ContextBundle:
    """
    Gather context using hybrid retrieval: selection + symbols + embeddings + graph neighbors.

    Priority order:
    1. Selection / active file (always included)
    2. Symbol-adjacent snippets
    3. Embedding-ranked chunks (with optional reranking)
    4. Graph neighbors of already-selected files

    Args:
        target_paths: Primary files to include.
        selection: Selected text (highest priority).
        symbol_query: Query for symbol-based context.
        user_query: Query for embedding search.
        budget_tokens: Maximum input tokens.
        weights: Optional weights for tie-breaking (symbol, embed, graph).

    Returns:
        ContextBundle with context, token usage, and metadata.
    """
    from indexer import build_or_load_symbols, query_symbols, build_or_load_embeddings, build_or_load_graph
    from indexer.rerank import get_reranker, Snippet
    from core.config import get_config

    config = get_config()

    # Default weights
    w_symbol = weights.get("symbol", 0.5) if weights else 0.5
    w_embed = weights.get("embed", 0.35) if weights else 0.35
    w_graph = weights.get("graph", 0.15) if weights else 0.15

    project_root = Path.cwd()
    sources = {"selection": 0, "symbol": 0, "embed": 0, "graph": 0}
    context_parts = []
    tokens_used = 0
    selected_files = set()

    # Reserve 20% for output
    output_margin = int(budget_tokens * 0.2)
    available_tokens = budget_tokens - output_margin

    # 1. Selection / active file (always include, clamp to 400-800 lines)
    if selection:
        selection_tokens = estimate_tokens(selection)
        if selection_tokens <= available_tokens:
            context_parts.append(f"Selected code:\n{selection}")
            tokens_used += selection_tokens
            sources["selection"] = 1
    else:
        # Include target files
        for path in target_paths[:2]:  # Limit primary files
            try:
                content = read_file(path, max_bytes=200_000)
                if content.startswith("Error:"):
                    continue
                lines = content.splitlines()
                if len(lines) > 400:
                    # Take first 400 + last 200 if very long
                    if len(lines) > 800:
                        content = "\n".join(lines[:400] + ["... (truncated) ..."] + lines[-200:])
                    else:
                        content = "\n".join(lines[:400]) + "\n... (truncated)"
                file_tokens = estimate_tokens(content)
                if tokens_used + file_tokens <= available_tokens:
                    context_parts.append(f"File: {path}\n{content}")
                    tokens_used += file_tokens
                    selected_files.add(path)
                    sources["selection"] += 1
            except Exception:
                continue

    # 2. Symbol-adjacent snippets
    if symbol_query and tokens_used < available_tokens:
        symbols_index = build_or_load_symbols(project_root)
        symbols = query_symbols(symbols_index, symbol_query)

        for symbol in symbols[:5]:  # Top 5 symbols
            if tokens_used >= available_tokens:
                break
            try:
                content = read_file(symbol.path, max_bytes=100_000)
                if content.startswith("Error:"):
                    continue

                lines = content.splitlines()
                start = max(0, symbol.start_line - 6)
                end = min(len(lines), symbol.end_line + 4)
                snippet = "\n".join(lines[start:end])
                snippet_tokens = estimate_tokens(snippet)

                if tokens_used + snippet_tokens <= available_tokens:
                    context_parts.append(f"Symbol: {symbol.name} ({symbol.kind}) in {symbol.path}\n{snippet}")
                    tokens_used += snippet_tokens
                    selected_files.add(symbol.path)
                    sources["symbol"] += 1
            except Exception:
                continue

    # 3. Embedding hits (with optional reranking)
    if user_query and tokens_used < available_tokens:
        emb_index = build_or_load_embeddings(project_root)
        if emb_index.vectors is not None:
            # Get initial candidates
            initial_hits = emb_index.search(user_query, k=config.retrieval_rerank_top_k or 50)

            # Convert to Snippets for reranking
            candidates = []
            for hit in initial_hits:
                try:
                    # Get text content for reranking
                    content = read_file(hit.path, max_bytes=50_000)
                    if content.startswith("Error:"):
                        continue

                    lines = content.splitlines()
                    start = max(0, hit.start_line - 3)
                    end = min(len(lines), hit.end_line + 3)
                    text = "\n".join(lines[start:end])

                    candidates.append(Snippet(
                        path=hit.path,
                        start_line=hit.start_line,
                        end_line=hit.end_line,
                        text=text,
                        score=hit.score
                    ))
                except Exception:
                    continue

            # Apply reranking if configured
            reranker_type = getattr(config, 'retrieval_reranker', 'bm25')
            if reranker_type != 'none' and candidates:
                reranker = get_reranker(reranker_type)
                reranked_candidates = reranker.rerank(user_query, candidates)
                # Sort by rerank_score, then by original score
                reranked_candidates.sort(key=lambda x: (x.rerank_score, x.score), reverse=True)
            else:
                reranked_candidates = candidates

            # Add top reranked results
            for snippet in reranked_candidates:
                if tokens_used >= available_tokens or snippet.path in selected_files:
                    continue

                snippet_tokens = estimate_tokens(snippet.text)
                if tokens_used + snippet_tokens <= available_tokens:
                    context_parts.append(f"Related: {snippet.path}:{snippet.start_line+1}\n{snippet.text}")
                    tokens_used += snippet_tokens
                    selected_files.add(snippet.path)
                    sources["embed"] += 1

    # 4. Graph neighbors
    if selected_files and tokens_used < available_tokens:
        graph_index = build_or_load_graph(project_root)
        seeds = list(selected_files)
        neighbors = graph_index.neighbors(seeds, depth=1, max_nodes=10)

        for neighbor_path in neighbors:
            if (tokens_used >= available_tokens or
                neighbor_path in selected_files or
                len([p for p in selected_files if p == neighbor_path]) >= 2):  # Limit per file
                continue
            try:
                content = read_file(neighbor_path, max_bytes=30_000)
                if content.startswith("Error:"):
                    continue

                lines = content.splitlines()
                if len(lines) > 60:
                    content = "\n".join(lines[:30] + ["..."] + lines[-30:])
                file_tokens = estimate_tokens(content)

                if tokens_used + file_tokens <= available_tokens:
                    context_parts.append(f"Related file: {neighbor_path}\n{content}")
                    tokens_used += file_tokens
                    selected_files.add(neighbor_path)
                    sources["graph"] += 1
            except Exception:
                continue

    # Calculate truncation ratio
    total_budget = budget_tokens
    truncation_ratio = tokens_used / total_budget if total_budget > 0 else 0.0

    return ContextBundle(
        context="\n\n".join(context_parts),
        tokens_used=tokens_used,
        sources=sources,
        truncation_ratio=truncation_ratio
    )