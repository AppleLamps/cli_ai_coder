"""Symbol indexer for Python and JS/TS files."""

import ast
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.config import get_config


class SymbolSpan:
    """Represents a symbol with its location."""

    def __init__(self, path: str, kind: str, name: str, start_line: int, end_line: int):
        self.path = path
        self.kind = kind  # 'module', 'class', 'function', etc.
        self.name = name
        self.start_line = start_line
        self.end_line = end_line

    def to_dict(self) -> Dict:
        """Convert to dict for serialization."""
        return {
            "path": self.path,
            "kind": self.kind,
            "name": self.name,
            "start_line": self.start_line,
            "end_line": self.end_line
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'SymbolSpan':
        """Create from dict."""
        return cls(
            path=data["path"],
            kind=data["kind"],
            name=data["name"],
            start_line=data["start_line"],
            end_line=data["end_line"]
        )


class SymbolsIndex:
    """Index of symbols across the project."""

    def __init__(self):
        self.symbols: List[SymbolSpan] = []
        self.file_mtimes: Dict[str, float] = {}

    def add_symbol(self, symbol: SymbolSpan):
        """Add a symbol to the index."""
        self.symbols.append(symbol)

    def query(self, query: str, lang_hint: Optional[str] = None) -> List[Tuple[SymbolSpan, float]]:
        """
        Query symbols with scoring.

        Returns list of (symbol, score) tuples, sorted by score desc.
        """
        results = []
        query_lower = query.lower()

        for symbol in self.symbols:
            # Skip if language hint doesn't match
            if lang_hint and not self._matches_language(symbol.path, lang_hint):
                continue

            name_lower = symbol.name.lower()
            score = 0.0

            # Exact match gets highest score
            if name_lower == query_lower:
                score = 1.0
            # Prefix match
            elif name_lower.startswith(query_lower):
                score = 0.8
            # Contains match
            elif query_lower in name_lower:
                score = 0.5
            else:
                continue

            # Boost for functions and classes
            if symbol.kind in ('function', 'class'):
                score += 0.1

            results.append((symbol, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:10]  # Top 10

    def _matches_language(self, path: str, lang_hint: str) -> bool:
        """Check if file matches language hint."""
        if lang_hint == 'python' and path.endswith('.py'):
            return True
        if lang_hint in ('javascript', 'typescript') and path.endswith(('.js', '.ts', '.jsx', '.tsx')):
            return True
        return False

    def save_to_file(self, path: Path):
        """Save index to file."""
        data = {
            "symbols": [s.to_dict() for s in self.symbols],
            "file_mtimes": self.file_mtimes
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_from_file(cls, path: Path) -> 'SymbolsIndex':
        """Load index from file."""
        with open(path, 'r') as f:
            data = json.load(f)

        index = cls()
        index.symbols = [SymbolSpan.from_dict(s) for s in data["symbols"]]
        index.file_mtimes = data["file_mtimes"]
        return index


class PythonIndexer:
    """Indexes Python files using AST."""

    def index_file(self, path: str, content: str) -> List[SymbolSpan]:
        """Index symbols in a Python file."""
        symbols = []
        try:
            tree = ast.parse(content, filename=path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    symbols.append(SymbolSpan(
                        path=path,
                        kind='class',
                        name=node.name,
                        start_line=node.lineno,
                        end_line=getattr(node, 'end_lineno', node.lineno)
                    ))
                elif isinstance(node, ast.FunctionDef):
                    symbols.append(SymbolSpan(
                        path=path,
                        kind='function',
                        name=node.name,
                        start_line=node.lineno,
                        end_line=getattr(node, 'end_lineno', node.lineno)
                    ))
        except SyntaxError:
            pass  # Skip files with syntax errors
        return symbols


class JSTSIndexer:
    """Basic indexer for JS/TS files using regex."""

    def index_file(self, path: str, content: str) -> List[SymbolSpan]:
        """Index symbols in a JS/TS file using regex."""
        symbols = []
        lines = content.splitlines()

        # Simple patterns
        patterns = [
            (r'^\s*function\s+(\w+)', 'function'),
            (r'^\s*class\s+(\w+)', 'class'),
            (r'^\s*export\s+(?:function|class|const|let|var)\s+(\w+)', 'export'),
            (r'^\s*(?:const|let|var)\s+(\w+)\s*=', 'variable'),
        ]

        for i, line in enumerate(lines, 1):
            for pattern, kind in patterns:
                match = re.match(pattern, line)
                if match:
                    name = match.group(1)
                    # Estimate end line (next blank line or 5 lines)
                    end_line = i
                    for j in range(i, min(i + 5, len(lines))):
                        if not lines[j].strip():
                            end_line = j
                            break
                    symbols.append(SymbolSpan(
                        path=path,
                        kind=kind,
                        name=name,
                        start_line=i,
                        end_line=end_line
                    ))
                    break  # Only one symbol per line

        return symbols


def build_or_load_symbols(project_root: Path) -> SymbolsIndex:
    """Build or load symbols index for the project."""
    config = get_config()
    if not config.index_enabled:
        return SymbolsIndex()  # Empty index if disabled

    index_dir = project_root / ".cli_ai_coder" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / "symbols.json"

    index = SymbolsIndex()

    # Find all relevant files
    python_files = list(project_root.rglob("*.py"))
    jsts_files = list(project_root.rglob("*.js")) + list(project_root.rglob("*.ts")) + \
                 list(project_root.rglob("*.jsx")) + list(project_root.rglob("*.tsx"))

    # Check if we need to rebuild
    needs_rebuild = not index_file.exists()
    if not needs_rebuild:
        try:
            index = SymbolsIndex.load_from_file(index_file)
            # Check mtimes
            for files in [python_files, jsts_files]:
                for file_path in files:
                    rel_path = str(file_path.relative_to(project_root))
                    current_mtime = file_path.stat().st_mtime
                    if index.file_mtimes.get(rel_path) != current_mtime:
                        needs_rebuild = True
                        break
                if needs_rebuild:
                    break
        except Exception:
            needs_rebuild = True

    if needs_rebuild:
        index = SymbolsIndex()
        python_indexer = PythonIndexer()
        jsts_indexer = JSTSIndexer()

        for file_path in python_files:
            try:
                rel_path = str(file_path.relative_to(project_root))
                content = file_path.read_text(encoding='utf-8')
                symbols = python_indexer.index_file(rel_path, content)
                for symbol in symbols:
                    index.add_symbol(symbol)
                index.file_mtimes[rel_path] = file_path.stat().st_mtime
            except Exception:
                pass

        for file_path in jsts_files:
            try:
                rel_path = str(file_path.relative_to(project_root))
                content = file_path.read_text(encoding='utf-8')
                symbols = jsts_indexer.index_file(rel_path, content)
                for symbol in symbols:
                    index.add_symbol(symbol)
                index.file_mtimes[rel_path] = file_path.stat().st_mtime
            except Exception:
                pass

        index.save_to_file(index_file)

    return index


def update_symbols_for_file(index: SymbolsIndex, project_root: Path, rel_path: str, event_type: str) -> bool:
    """
    Update symbols index for a specific file change.

    Args:
        index: The symbols index to update
        project_root: Project root path
        rel_path: Relative path of the changed file
        event_type: 'created', 'modified', or 'deleted'

    Returns:
        True if index was modified
    """
    if event_type == 'deleted':
        # Remove all symbols from this file
        index.symbols = [s for s in index.symbols if s.path != rel_path]
        if rel_path in index.file_mtimes:
            del index.file_mtimes[rel_path]
        return True

    elif event_type in ('created', 'modified'):
        # Remove existing symbols for this file
        index.symbols = [s for s in index.symbols if s.path != rel_path]

        # Re-index the file
        file_path = project_root / rel_path
        if file_path.exists():
            try:
                content = file_path.read_text(encoding='utf-8')

                if rel_path.endswith('.py'):
                    indexer = PythonIndexer()
                elif rel_path.endswith(('.js', '.ts', '.jsx', '.tsx')):
                    indexer = JSTSIndexer()
                else:
                    return False

                symbols = indexer.index_file(rel_path, content)
                for symbol in symbols:
                    index.add_symbol(symbol)
                index.file_mtimes[rel_path] = file_path.stat().st_mtime
                return True

            except Exception:
                # On error, remove file from index
                if rel_path in index.file_mtimes:
                    del index.file_mtimes[rel_path]
                return True

    return False


def query_symbols(index: SymbolsIndex, query: str, lang_hint: Optional[str] = None) -> List[SymbolSpan]:
    """Query symbols from index."""
    results = index.query(query, lang_hint)
    return [symbol for symbol, score in results]