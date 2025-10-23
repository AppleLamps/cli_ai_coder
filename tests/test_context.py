"""Tests for context packing."""

import pytest
from unittest.mock import patch

from ai.context import gather_context, estimate_tokens


def test_estimate_tokens():
    """Test token estimation."""
    text = "hello world"
    tokens = estimate_tokens(text)
    assert tokens == 2  # 10 chars / 4 = 2.5, but should be int


def test_gather_context_with_selection():
    """Test context gathering with selection."""
    with patch('ai.context.repo_search') as mock_search, \
         patch('ai.context.read_file') as mock_read:

        mock_search.return_value = [("file1.py", 0.8), ("file2.py", 0.7)]
        mock_read.return_value = "def func():\n    pass"

        result = gather_context(
            target_paths=["main.py"],
            selection="selected code",
            extra_queries=["test"],
            max_tokens=100
        )

        assert "selected code" in result["context"]
        assert result["tokens_used"] > 0
        assert result["tokens_used"] <= 100


def test_gather_context_budget_respected():
    """Test that token budget is respected."""
    with patch('ai.context.repo_search') as mock_search, \
         patch('ai.context.read_file') as mock_read:

        mock_search.return_value = [("file1.py", 0.8)]
        mock_read.return_value = "x" * 1000  # Long content

        result = gather_context(
            target_paths=["main.py"],
            selection=None,
            extra_queries=[],
            max_tokens=50  # Very small budget
        )

        assert result["tokens_used"] <= 50