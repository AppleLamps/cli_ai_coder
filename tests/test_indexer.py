"""Tests for symbol indexer."""

import tempfile
from pathlib import Path

from indexer.symbols import build_or_load_symbols, query_symbols, SymbolsIndex, SymbolSpan


def test_symbol_span():
    """Test SymbolSpan."""
    span = SymbolSpan("test.py", "function", "test_func", 10, 20)
    assert span.path == "test.py"
    assert span.kind == "function"
    assert span.name == "test_func"
    assert span.start_line == 10
    assert span.end_line == 20

    # Test serialization
    data = span.to_dict()
    span2 = SymbolSpan.from_dict(data)
    assert span2.path == span.path


def test_symbols_index():
    """Test SymbolsIndex."""
    index = SymbolsIndex()

    span1 = SymbolSpan("a.py", "class", "A", 1, 10)
    span2 = SymbolSpan("b.py", "function", "func", 5, 15)

    index.add_symbol(span1)
    index.add_symbol(span2)

    results = index.query("A")
    assert len(results) == 1
    assert results[0][0].name == "A"

    results = index.query("func")
    assert len(results) == 1
    assert results[0][0].name == "func"


def test_python_indexer():
    """Test Python indexer."""
    from indexer.symbols import PythonIndexer

    indexer = PythonIndexer()
    code = """
class TestClass:
    def __init__(self):
        pass

    def method(self):
        pass

def standalone_func():
    pass
"""
    symbols = indexer.index_file("test.py", code)

    assert len(symbols) == 4
    names = [s.name for s in symbols]
    assert "TestClass" in names
    assert "__init__" in names
    assert "method" in names
    assert "standalone_func" in names


def test_build_or_load_symbols():
    """Test building symbols index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Create test files
        (project_root / "test.py").write_text("""
class MyClass:
    def method(self):
        pass

def func():
    pass
""")

        index = build_or_load_symbols(project_root)
        assert len(index.symbols) > 0

        # Query
        results = query_symbols(index, "MyClass")
        assert len(results) > 0
        assert results[0].name == "MyClass"


def test_context_gather_symbol_adjacent():
    """Test gather_symbol_adjacent_snippets."""
    import os
    from ai.context import gather_symbol_adjacent_snippets

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        old_cwd = os.getcwd()

        try:
            os.chdir(tmpdir)

            # Create test file
            (project_root / "test.py").write_text("""
class MyClass:
    def method(self):
        print("hello")

def func():
        print("world")
""")

            # Build index
            from indexer.symbols import build_or_load_symbols
            index = build_or_load_symbols(project_root)

            # Gather context
            context = gather_symbol_adjacent_snippets(["test.py"], "MyClass", 1000)
            assert "tokens_used" in context
            assert context["tokens_used"] > 0
        finally:
            os.chdir(old_cwd)