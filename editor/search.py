"""Fuzzy and regex repo search."""

import os
from pathlib import Path
from typing import Callable, List, Tuple

try:
    from rapidfuzz import fuzz, process
except ImportError:
    # Fallback implementation
    def fuzz_ratio(a: str, b: str) -> float:
        return 0.0

    class process:
        @staticmethod
        def extract(query: str, choices: List[str], limit: int = 5) -> List[Tuple[str, float, int]]:
            return [(choice, 0.0, i) for i, choice in enumerate(choices[:limit])]


def get_project_files() -> List[str]:
    """
    Get all files in the project (excluding common ignores).

    Returns:
        List of relative file paths.
    """
    cwd = Path.cwd()
    files = []

    ignore_patterns = {
        '__pycache__', '.git', '.venv', 'node_modules', '.DS_Store',
        '*.pyc', '*.pyo', '*.pyd', '.pytest_cache', '.tox'
    }

    for root, dirs, filenames in os.walk(cwd):
        # Filter directories
        dirs[:] = [d for d in dirs if d not in ignore_patterns and not d.startswith('.')]

        for filename in filenames:
            if filename.startswith('.') or any(filename.endswith(pat) for pat in ['.pyc', '.pyo', '.pyd']):
                continue

            rel_path = Path(root).relative_to(cwd) / filename
            files.append(str(rel_path))

    return files


def fuzzy_search_files(query: str, files: List[str], limit: int = 10) -> List[Tuple[str, float]]:
    """
    Perform fuzzy search on file list.

    Args:
        query: Search query.
        files: List of file paths to search.
        limit: Maximum results.

    Returns:
        List of (file_path, score) tuples.
    """
    if not query.strip():
        return [(f, 1.0) for f in files[:limit]]

    # Extract best matches
    results = process.extract(query, files, scorer=fuzz.ratio, limit=limit)

    return [(match, score / 100.0) for match, score, _ in results]