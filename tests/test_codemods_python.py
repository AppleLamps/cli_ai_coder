"""Tests for Python codemods."""

import pytest
from pathlib import Path
from codemods.python_libcst import RenameSymbolCodemod, ConvertPrintToLoggingCodemod, AddTypeHintsCodemod


class TestRenameSymbolCodemod:
    """Test rename symbol codemod."""

    def test_preview_rename_function(self):
        """Test preview of renaming a function."""
        code = """
def old_function():
    return "hello"

result = old_function()
"""
        mod = RenameSymbolCodemod("old_function", "new_function")
        diff = mod.preview("test.py", code)
        assert "old_function" in diff
        assert "new_function" in diff

    def test_apply_rename_function(self):
        """Test applying rename to function."""
        code = """
def old_function():
    return "hello"

result = old_function()
"""
        expected = """
def new_function():
    return "hello"

result = new_function()
"""
        mod = RenameSymbolCodemod("old_function", "new_function")
        result = mod.apply("test.py", code)
        assert "old_function" not in result
        assert "new_function" in result


class TestConvertPrintToLoggingCodemod:
    """Test convert print to logging codemod."""

    def test_preview_print_to_logging(self):
        """Test preview of converting print to logging."""
        code = 'print("Hello world")\n'
        mod = ConvertPrintToLoggingCodemod("info")
        diff = mod.preview("test.py", code)
        assert "print" in diff
        assert "logging.info" in diff

    def test_apply_print_to_logging(self):
        """Test applying print to logging conversion."""
        code = 'print("Hello world")\n'
        expected = 'logging.info("Hello world")\n'
        mod = ConvertPrintToLoggingCodemod("info")
        result = mod.apply("test.py", code)
        assert "print" not in result
        assert "logging.info" in result


class TestAddTypeHintsCodemod:
    """Test add type hints codemod."""

    def test_preview_add_type_hints(self):
        """Test preview of adding type hints."""
        code = """
def greet(name):
    return f"Hello {name}"
"""
        mod = AddTypeHintsCodemod()
        diff = mod.preview("test.py", code)
        # Should add str type hint
        assert "str" in diff

    def test_apply_add_type_hints(self):
        """Test applying type hints addition."""
        code = """
def greet(name):
    return f"Hello {name}"
"""
        mod = AddTypeHintsCodemod()
        result = mod.apply("test.py", code)
        # Should add str type hint
        assert ": str" in result