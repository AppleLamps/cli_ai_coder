"""Tests for AI history functionality."""

import json
import tempfile
from pathlib import Path

import pytest

from ai.history import AIHistory, HistoryEntry


def test_history_entry_serialization():
    """Test HistoryEntry serialization."""
    entry = HistoryEntry(
        timestamp=1234567890.0,
        task_type="explain",
        model="grok-code-fast-1",
        input_files=["test.py"],
        token_metrics={"input": 100, "output": 50},
        tool_calls=[{"name": "read_file", "duration": 0.1}],
        response_hash="abc123",
        applied_patch=True
    )
    
    # Test to_dict
    data = entry.to_dict()
    assert data["timestamp"] == 1234567890.0
    assert data["task_type"] == "explain"
    assert data["model"] == "grok-code-fast-1"
    assert data["input_files"] == ["test.py"]
    assert data["token_metrics"] == {"input": 100, "output": 50}
    assert data["tool_calls"] == [{"name": "read_file", "duration": 0.1}]
    assert data["response_hash"] == "abc123"
    assert data["applied_patch"] is True
    
    # Test from_dict
    entry2 = HistoryEntry.from_dict(data)
    assert entry2.timestamp == entry.timestamp
    assert entry2.task_type == entry.task_type
    assert entry2.model == entry.model


def test_ai_history_disabled():
    """Test history when disabled."""
    # Create a new instance with disabled config
    from unittest.mock import patch
    with patch('ai.history.get_config') as mock_config:
        mock_config.return_value.history_enabled = False
        mock_config.return_value.history_max_entries = 1000
        history = AIHistory()
        assert not history.enabled


def test_ai_history_basic():
    """Test basic history operations."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Change to temp directory
        original_cwd = Path.cwd()
        import os
        os.chdir(temp_dir)
        
        try:
            history = AIHistory()
            assert history.enabled  # Should be enabled by default
            
            # Add entries
            history.add_entry(
                task_type="explain",
                model="grok-code-fast-1",
                input_files=["file1.py"],
                token_metrics={"input": 10, "output": 5},
                tool_calls=[],
                response_hash="hash1",
                applied_patch=False
            )
            
            import time
            time.sleep(0.01)  # Ensure different timestamps
            
            history.add_entry(
                task_type="refactor",
                model="grok-code-fast-1",
                input_files=["file2.py"],
                token_metrics={"input": 20, "output": 10},
                tool_calls=[{"name": "read_file", "duration": 0.2}],
                response_hash="hash2",
                applied_patch=True
            )
            
            # Check entries
            entries = history.get_entries()
            assert len(entries) == 2
            assert entries[0].task_type == "refactor"  # Most recent first
            assert entries[1].task_type == "explain"
            
            # Check stats
            stats = history.get_stats()
            assert stats["total_entries"] == 2
            assert stats["patches_applied"] == 1
            assert stats["total_tokens"] == 45  # 10+5+20+10
            
            # Test persistence
            history2 = AIHistory()
            entries2 = history2.get_entries()
            assert len(entries2) == 2
            
        finally:
            os.chdir(original_cwd)


def test_ai_history_max_entries():
    """Test max entries enforcement."""
    with tempfile.TemporaryDirectory() as temp_dir:
        original_cwd = Path.cwd()
        import os
        os.chdir(temp_dir)
        
        try:
            history = AIHistory()
            history.max_entries = 3
            
            # Add 5 entries
            for i in range(5):
                history.add_entry(
                    task_type=f"task{i}",
                    model="model",
                    input_files=[],
                    token_metrics={"input": i, "output": i},
                    tool_calls=[],
                    response_hash=f"hash{i}",
                    applied_patch=False
                )
                import time
                time.sleep(0.01)  # Ensure different timestamps
            
            # Should only keep last 3
            entries = history.get_entries()
            assert len(entries) == 3
            assert entries[0].task_type == "task4"  # Most recent
            assert entries[1].task_type == "task3"
            assert entries[2].task_type == "task2"  # Oldest kept
            
        finally:
            os.chdir(original_cwd)


def test_ai_history_clear():
    """Test clearing history."""
    with tempfile.TemporaryDirectory() as temp_dir:
        original_cwd = Path.cwd()
        import os
        os.chdir(temp_dir)
        
        try:
            history = AIHistory()
            
            # Add entry
            history.add_entry("test", "model", [], {}, [], None, False)
            assert len(history.entries) == 1
            
            # Clear
            history.clear_history()
            assert len(history.entries) == 0
            
            # Check persistence
            history2 = AIHistory()
            assert len(history2.entries) == 0
            
        finally:
            os.chdir(original_cwd)


def test_ai_history_command():
    """Test the ai-history command."""
    from editor.commands import ai_history
    from ai.history import history
    
    # Clear any existing history
    history.clear_history()
    
    # With no history, should return message
    result = ai_history()
    assert "No AI history available" in result
    
    # With history (mock)
    with tempfile.TemporaryDirectory() as temp_dir:
        original_cwd = Path.cwd()
        import os
        os.chdir(temp_dir)
        
        try:
            from ai.history import history
            history.add_entry(
                task_type="explain",
                model="grok-code-fast-1",
                input_files=["test.py"],
                token_metrics={"input": 100, "output": 50},
                tool_calls=[],
                response_hash="testhash",
                applied_patch=True
            )
            
            result = ai_history()
            assert "AI Interaction History" in result
            assert "explain" in result
            assert "grok-code-fast-1" in result
            assert "150t" in result  # 100+50
            assert "✓" in result  # Applied patch
            
        finally:
            os.chdir(original_cwd)