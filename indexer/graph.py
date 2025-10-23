"""Cross-file symbol graph for context expansion."""

import ast
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from core.config import get_config


class GraphIndex:
    """Cross-file symbol graph."""

    def __init__(self):
        self.nodes: List[str] = []  # file paths
        self.edges: List[Tuple[int, int, float]] = []  # (from_idx, to_idx, weight)
        self.node_map: Dict[str, int] = {}  # path -> index
        self.built_at: float = 0.0
        self.files: Dict[str, float] = {}  # path -> mtime

    def neighbors(self, seeds: List[str], depth: int = 1, max_nodes: int = 50) -> List[str]:
        """Get neighbors of seed files."""
        if not seeds or depth < 1:
            return seeds

        # Convert seeds to indices
        seed_indices = set()
        for seed in seeds:
            if seed in self.node_map:
                seed_indices.add(self.node_map[seed])

        if not seed_indices:
            return seeds

        # BFS to find neighbors
        visited = set(seed_indices)
        current = list(seed_indices)
        result_indices = set(seed_indices)

        for _ in range(depth):
            if len(result_indices) >= max_nodes:
                break
            next_level = set()
            for idx in current:
                if len(result_indices) >= max_nodes:
                    break
                # Find outgoing edges
                for from_idx, to_idx, weight in self.edges:
                    if from_idx == idx and to_idx not in visited:
                        next_level.add(to_idx)
                        visited.add(to_idx)
                        result_indices.add(to_idx)
                        if len(result_indices) >= max_nodes:
                            break
                if len(result_indices) >= max_nodes:
                    break
            if not next_level:
                break
            current = list(next_level)

        # Convert back to paths, limit to max_nodes
        result = []
        for idx in sorted(result_indices):
            if len(result) >= max_nodes:
                break
            if idx < len(self.nodes):
                result.append(self.nodes[idx])

        return result

    def save_to_file(self, path: Path):
        """Save graph to file."""
        data = {
            "nodes": self.nodes,
            "edges": self.edges,
            "built_at": self.built_at,
            "files": self.files
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_from_file(cls, path: Path) -> 'GraphIndex':
        """Load graph from file."""
        if not path.exists():
            return cls()

        with open(path, 'r') as f:
            data = json.load(f)

        graph = cls()
        graph.nodes = data["nodes"]
        graph.edges = [(e[0], e[1], e[2]) for e in data["edges"]]
        graph.built_at = data["built_at"]
        graph.files = data["files"]

        # Rebuild node map
        graph.node_map = {path: i for i, path in enumerate(graph.nodes)}

        return graph


class PythonGraphBuilder:
    """Builds import graph for Python files."""

    def __init__(self):
        self.imports: Dict[str, Set[str]] = defaultdict(set)  # file -> imported modules
        self.modules: Dict[str, str] = {}  # module -> file

    def process_file(self, path: str, content: str):
        """Process a Python file for imports."""
        try:
            tree = ast.parse(content, filename=path)
            imports = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split('.')[0])

            self.imports[path] = imports

            # Try to infer module name from path
            rel_path = Path(path)
            if rel_path.suffix == '.py':
                module_name = rel_path.stem
                self.modules[module_name] = path

        except SyntaxError:
            pass

    def build_graph(self) -> GraphIndex:
        """Build the graph from collected imports."""
        graph = GraphIndex()
        graph.nodes = list(self.imports.keys())
        graph.node_map = {path: i for i, path in enumerate(graph.nodes)}

        # Create edges based on imports
        for from_path, imported_modules in self.imports.items():
            from_idx = graph.node_map[from_path]

            for module in imported_modules:
                if module in self.modules:
                    to_path = self.modules[module]
                    if to_path in graph.node_map:
                        to_idx = graph.node_map[to_path]
                        # Add edge with weight 1.0 for direct imports
                        graph.edges.append((from_idx, to_idx, 1.0))

        return graph


class JSTSGraphBuilder:
    """Builds import graph for JS/TS files."""

    def __init__(self):
        self.imports: Dict[str, Set[str]] = defaultdict(set)  # file -> imported modules
        self.modules: Dict[str, str] = {}  # module -> file

    def process_file(self, path: str, content: str):
        """Process a JS/TS file for imports."""
        imports = set()
        lines = content.splitlines()

        # Simple regex patterns for imports
        patterns = [
            r'import\s+.*?\s+from\s+["\']([^"\']+)["\']',
            r'import\s*\(\s*["\']([^"\']+)["\']',
            r'require\s*\(\s*["\']([^"\']+)["\']',
            r'export\s+.*?\s+from\s+["\']([^"\']+)["\']'
        ]

        for line in lines:
            for pattern in patterns:
                matches = re.findall(pattern, line)
                for match in matches:
                    # Extract module name (remove file extensions, take first part)
                    module = match.split('/')[0]
                    if module and not module.startswith('.'):
                        imports.add(module)

        self.imports[path] = imports

        # Infer module name from filename
        rel_path = Path(path)
        if rel_path.suffix in ('.js', '.ts', '.jsx', '.tsx'):
            module_name = rel_path.stem
            self.modules[module_name] = path

    def build_graph(self) -> GraphIndex:
        """Build the graph from collected imports."""
        graph = GraphIndex()
        graph.nodes = list(self.imports.keys())
        graph.node_map = {path: i for i, path in enumerate(graph.nodes)}

        # Create edges based on imports
        for from_path, imported_modules in self.imports.items():
            from_idx = graph.node_map[from_path]

            for module in imported_modules:
                if module in self.modules:
                    to_path = self.modules[module]
                    if to_path in graph.node_map:
                        to_idx = graph.node_map[to_path]
                        # Add edge with weight 1.0 for direct imports
                        graph.edges.append((from_idx, to_idx, 1.0))

        return graph


def build_or_load_graph(project_root: Path, force: bool = False) -> GraphIndex:
    """Build or load symbol graph."""
    config = get_config()
    if not config.index_enabled:
        return GraphIndex()

    index_dir = project_root / ".cli_ai_coder" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    graph_file = index_dir / "graph.json"

    # Check if rebuild needed
    needs_rebuild = force or not graph_file.exists()

    if not needs_rebuild:
        try:
            graph = GraphIndex.load_from_file(graph_file)
            # Check for file changes
            for root, dirs, files in os.walk(project_root):
                for file in files:
                    if file.endswith(('.py', '.js', '.ts', '.jsx', '.tsx')):
                        file_path = Path(root) / file
                        rel_path = str(file_path.relative_to(project_root))

                        current_mtime = file_path.stat().st_mtime
                        if graph.files.get(rel_path) != current_mtime:
                            needs_rebuild = True
                            break
                if needs_rebuild:
                    break
        except Exception:
            needs_rebuild = True

    if needs_rebuild:
        graph = _build_graph(project_root)
        graph.save_to_file(graph_file)

    return graph


def _build_graph(project_root: Path) -> GraphIndex:
    """Build graph from scratch."""
    python_builder = PythonGraphBuilder()
    jsts_builder = JSTSGraphBuilder()

    # Process all files
    for root, dirs, files in os.walk(project_root):
        for file in files:
            file_path = Path(root) / file
            rel_path = str(file_path.relative_to(project_root))

            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')

                if file.endswith('.py'):
                    python_builder.process_file(rel_path, content)
                elif file.endswith(('.js', '.ts', '.jsx', '.tsx')):
                    jsts_builder.process_file(rel_path, content)

                # Track mtime
                python_builder.imports[rel_path]  # Ensure file is tracked even if no imports
                jsts_builder.imports[rel_path]

            except Exception:
                continue

    # Combine graphs (prefer Python for .py files)
    combined = GraphIndex()
    all_files = set(python_builder.imports.keys()) | set(jsts_builder.imports.keys())
    combined.nodes = sorted(all_files)
    combined.node_map = {path: i for i, path in enumerate(combined.nodes)}
    combined.built_at = __import__('time').time()

    # Add edges from both builders
    all_edges = set()

    # Python edges
    for from_path, imports in python_builder.imports.items():
        if from_path in combined.node_map:
            from_idx = combined.node_map[from_path]
            for module in imports:
                if module in python_builder.modules:
                    to_path = python_builder.modules[module]
                    if to_path in combined.node_map:
                        to_idx = combined.node_map[to_path]
                        all_edges.add((from_idx, to_idx, 1.0))

    # JS/TS edges
    for from_path, imports in jsts_builder.imports.items():
        if from_path in combined.node_map:
            from_idx = combined.node_map[from_path]
            for module in imports:
                if module in jsts_builder.modules:
                    to_path = jsts_builder.modules[module]
                    if to_path in combined.node_map:
                        to_idx = combined.node_map[to_path]
                        all_edges.add((from_idx, to_idx, 1.0))

    combined.edges = list(all_edges)

    # Track file mtimes
    for file_path in all_files:
        full_path = project_root / file_path
        if full_path.exists():
            combined.files[file_path] = full_path.stat().st_mtime

    return combined


def update_graph_for_file(graph: GraphIndex, project_root: Path, rel_path: str, event_type: str) -> bool:
    """
    Update graph index for a specific file change.

    Args:
        graph: The graph index to update
        project_root: Project root path
        rel_path: Relative path of the changed file
        event_type: 'created', 'modified', or 'deleted'

    Returns:
        True if graph was modified
    """
    if event_type == 'deleted':
        # Remove node and related edges
        if rel_path in graph.node_map:
            node_idx = graph.node_map[rel_path]

            # Remove edges involving this node
            graph.edges = [
                (from_idx, to_idx, weight)
                for from_idx, to_idx, weight in graph.edges
                if from_idx != node_idx and to_idx != node_idx
            ]

            # Remove node
            del graph.node_map[rel_path]
            graph.nodes.remove(rel_path)

            # Update indices for remaining nodes
            graph.node_map = {path: i for i, path in enumerate(graph.nodes)}

            # Update edge indices
            new_edges = []
            for from_idx, to_idx, weight in graph.edges:
                if from_idx > node_idx:
                    from_idx -= 1
                if to_idx > node_idx:
                    to_idx -= 1
                new_edges.append((from_idx, to_idx, weight))
            graph.edges = new_edges

            if rel_path in graph.files:
                del graph.files[rel_path]

            return True

    elif event_type in ('created', 'modified'):
        file_path = project_root / rel_path
        if not file_path.exists():
            return False

        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')

            # Determine builder type
            if rel_path.endswith('.py'):
                builder = PythonGraphBuilder()
            elif rel_path.endswith(('.js', '.ts', '.jsx', '.tsx')):
                builder = JSTSGraphBuilder()
            else:
                return False

            # Process the file
            builder.process_file(rel_path, content)

            # Remove existing edges from this file
            if rel_path in graph.node_map:
                node_idx = graph.node_map[rel_path]
                graph.edges = [
                    (from_idx, to_idx, weight)
                    for from_idx, to_idx, weight in graph.edges
                    if from_idx != node_idx
                ]
            else:
                # Add new node
                graph.nodes.append(rel_path)
                graph.node_map[rel_path] = len(graph.nodes) - 1
                node_idx = graph.node_map[rel_path]

            # Add new edges
            for module in builder.imports.get(rel_path, set()):
                if module in builder.modules:
                    to_path = builder.modules[module]
                    if to_path in graph.node_map:
                        to_idx = graph.node_map[to_path]
                        graph.edges.append((node_idx, to_idx, 1.0))

            # Update mtime
            graph.files[rel_path] = file_path.stat().st_mtime

            return True

        except Exception:
            return False

    return False

