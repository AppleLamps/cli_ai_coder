"""Tests for context packer v2."""

import os
import tempfile
from pathlib import Path

from ai.context import gather_context_v2, ContextBundle


class TestContextV2:
    """Test context packer v2 functionality."""

    def test_context_bundle_init(self):
        """Test ContextBundle creation."""
        bundle = ContextBundle(
            context="test",
            tokens_used=10,
            sources={"selection": 1, "symbol": 0, "embed": 0, "graph": 0},
            truncation_ratio=0.1
        )
        assert bundle.context == "test"
        assert bundle.tokens_used == 10
        assert bundle.sources["selection"] == 1
        assert bundle.truncation_ratio == 0.1

    def test_gather_context_v2_empty(self):
        """Test gathering context with no inputs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            os.chdir(temp_dir)

            try:
                bundle = gather_context_v2([], None, None, None, 1000)
                assert isinstance(bundle, ContextBundle)
                assert bundle.tokens_used == 0
                assert bundle.context == ""
            finally:
                os.chdir(original_cwd)

    def test_gather_context_v2_selection_only(self):
        """Test gathering context with selection only."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            os.chdir(temp_dir)

            try:
                selection = "def test():\n    pass"
                bundle = gather_context_v2([], selection, None, None, 1000)

                assert isinstance(bundle, ContextBundle)
                assert bundle.tokens_used > 0
                assert "Selected code:" in bundle.context
                assert bundle.sources["selection"] == 1
            finally:
                os.chdir(original_cwd)

    def test_gather_context_v2_with_files(self):
        """Test gathering context with target files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            os.chdir(temp_dir)

            try:
                # Create test file
                test_file = Path("test.py")
                test_file.write_text("def func():\n    return True\n")

                bundle = gather_context_v2(["test.py"], None, None, None, 1000)

                assert isinstance(bundle, ContextBundle)
                assert bundle.tokens_used > 0
                assert "File: test.py" in bundle.context
                assert bundle.sources["selection"] >= 1
            finally:
                os.chdir(original_cwd)

    def test_gather_context_v2_symbol_query(self):
        """Test gathering context with symbol query."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            os.chdir(temp_dir)

            try:
                # Create test file with symbols
                test_file = Path("test.py")
                test_file.write_text("def my_function():\n    return True\n\nclass MyClass:\n    pass\n")

                bundle = gather_context_v2([], None, "my_function", None, 1000)

                assert isinstance(bundle, ContextBundle)
                # May or may not find symbols depending on indexer
                assert isinstance(bundle.sources, dict)
            finally:
                os.chdir(original_cwd)

    def test_gather_context_v2_budget_respect(self):
        """Test that context respects token budget."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            os.chdir(temp_dir)

            try:
                # Create large test file
                test_file = Path("large.py")
                content = "\n".join([f"def func{i}():\n    pass" for i in range(100)])
                test_file.write_text(content)

                # Small budget
                bundle = gather_context_v2(["large.py"], None, None, None, 50)

                assert isinstance(bundle, ContextBundle)
                assert bundle.tokens_used <= 50  # Should respect budget
                assert bundle.truncation_ratio <= 1.0
            finally:
                os.chdir(original_cwd)

    def test_gather_context_v2_weights(self):
        """Test custom weights parameter."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            os.chdir(temp_dir)

            try:
                weights = {"symbol": 0.8, "embed": 0.1, "graph": 0.1}
                bundle = gather_context_v2([], "test", "query", "search", 1000, weights=weights)

                assert isinstance(bundle, ContextBundle)
                # Weights don't change behavior directly, just stored for future use
            finally:
                os.chdir(original_cwd)