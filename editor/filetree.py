"""File browser."""

import os
from pathlib import Path
from typing import Dict, List, Optional


def get_directory_tree(root_path: Path) -> Dict[str, List[str]]:
    """
    Get a directory tree structure.

    Args:
        root_path: Root directory path.

    Returns:
        Dict mapping directory paths to lists of items (files and subdirs).
    """
    tree = {}

    ignore_patterns = {
        '__pycache__', '.git', '.venv', 'node_modules', '.DS_Store',
        '.pytest_cache', '.tox'
    }

    for root, dirs, files in os.walk(root_path):
        # Filter directories
        dirs[:] = [d for d in dirs if d not in ignore_patterns and not d.startswith('.')]

        rel_root = Path(root).relative_to(root_path)
        items = []

        # Add subdirectories
        for d in sorted(dirs):
            items.append(f"📁 {d}/")

        # Add files
        for f in sorted(files):
            if not f.startswith('.') and not any(f.endswith(pat) for pat in ['.pyc', '.pyo', '.pyd']):
                items.append(f"📄 {f}")

        if items:
            tree[str(rel_root)] = items

    return tree


def flatten_tree_for_display(tree: Dict[str, List[str]], max_depth: int = 3) -> List[str]:
    """
    Flatten tree structure for display.

    Args:
        tree: Directory tree from get_directory_tree.
        max_depth: Maximum directory depth to show.

    Returns:
        List of display lines.
    """
    lines = []
    root_path = Path.cwd()

    def add_directory(path: str, indent: str = "", depth: int = 0):
        if depth > max_depth:
            return

        if path in tree:
            for item in tree[path]:
                lines.append(f"{indent}{item}")
                if item.endswith('/') and depth < max_depth:
                    subdir = (Path(path) / item[2:-1]).relative_to(root_path)
                    add_directory(str(subdir), indent + "  ", depth + 1)

    add_directory(".")
    return lines