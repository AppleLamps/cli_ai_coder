"""Tool shims for AI agentic use."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

try:
    from rapidfuzz import fuzz, process
except ImportError:
    # Fallback if rapidfuzz not available
    def fuzz_ratio(a: str, b: str) -> float:
        return 0.0
    process = None


def repo_search(query: str, globs: List[str] = None, limit: int = 5) -> List[Tuple[str, float]]:
    """
    Search project files for relevant content.

    Args:
        query: Search query.
        globs: Optional file patterns to search in.
        limit: Maximum results to return.

    Returns:
        List of (path, score) tuples.
    """
    if globs is None:
        globs = ["**/*.py", "**/*.txt", "**/*.md"]

    results = []
    cwd = Path.cwd()

    for glob_pattern in globs:
        for file_path in cwd.glob(glob_pattern):
            if file_path.is_file() and _is_path_allowed(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        score = fuzz_ratio(query.lower(), content.lower())
                        if score > 0.1:  # Minimum threshold
                            results.append((str(file_path.relative_to(cwd)), score))
                except Exception:
                    continue

    # Sort by score descending and return top limit
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:limit]


def run_tests() -> dict:
    """
    Run pytest and return results as JSON.

    Returns:
        Dict with exit_code, stdout, stderr.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.getcwd()
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "Tests timed out"
        }
    except Exception as e:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Error running tests: {e}"
        }


def read_file(path: str, max_bytes: int = 200_000) -> str:
    """
    Read file content for targeted access.

    Args:
        path: File path relative to project root.
        max_bytes: Maximum bytes to read.

    Returns:
        File content as string.
    """
    cwd = Path.cwd()
    full_path = (cwd / path).resolve()

    # Security check: ensure path is within project root
    if not _is_path_allowed(full_path):
        return f"Error: Access denied to path outside project root: {path}"

    if not full_path.is_file():
        return f"Error: File not found: {path}"

    try:
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(max_bytes)
            if len(content) == max_bytes:
                content += "\n... (truncated)"
            return content
    except Exception as e:
        return f"Error reading file: {e}"


def _is_path_allowed(path: Path) -> bool:
    """Check if path is within project root and not in ignored directories."""
    cwd = Path.cwd()
    try:
        path.resolve().relative_to(cwd.resolve())
    except ValueError:
        return False

    # Check .gitignore if it exists
    gitignore = cwd / ".gitignore"
    if gitignore.exists():
        try:
            with open(gitignore, 'r', encoding='utf-8') as f:
                ignored = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                rel_path = path.relative_to(cwd)
                for pattern in ignored:
                    if pattern in str(rel_path):
                        return False
        except Exception:
            pass  # If gitignore can't be read, allow access

    return True


def exec_py(code: str, timeout_s: int = 3) -> Tuple[int, str, str]:
    """
    Execute Python code in a subprocess.

    Args:
        code: Python code to execute.
        timeout_s: Timeout in seconds.

    Returns:
        Tuple of (exit_code, stdout, stderr).
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=os.getcwd()
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Execution timed out"
    except Exception as e:
        return -1, "", f"Error executing code: {e}"