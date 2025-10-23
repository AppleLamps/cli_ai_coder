"""Tests for file system watcher."""

import os
import tempfile
import time
from pathlib import Path
import pytest

from indexer.watch import IndexWatcher, FileChangeEvent


class TestIndexWatcher:
    """Test the IndexWatcher functionality."""

    def test_file_change_event(self):
        """Test FileChangeEvent creation."""
        event = FileChangeEvent("test.py", "modified")
        assert event.path == "test.py"
        assert event.event_type == "modified"
        assert not event.is_dir
        assert isinstance(event.timestamp, float)

    def test_watcher_initialization(self):
        """Test watcher initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            watcher = IndexWatcher(project_root)

            assert watcher.project_root == project_root
            assert watcher.enabled
            assert watcher.debounce_ms == 100
            assert watcher.polling_fallback
            assert watcher.polling_interval_ms == 1500

    def test_should_watch_file(self):
        """Test file filtering logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = IndexWatcher(Path(tmpdir))

            # Should watch Python files
            assert watcher._should_watch_file("test.py")
            assert watcher._should_watch_file("module.js")

            # Should not watch binary files
            assert not watcher._should_watch_file("image.png")
            assert not watcher._should_watch_file("data.bin")

    def test_is_ignored_path(self):
        """Test path ignoring logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            watcher = IndexWatcher(project_root)

            # Should ignore .git files
            assert watcher._is_ignored_path(str(project_root / ".git" / "config"))
            assert watcher._is_ignored_path(str(project_root / "subdir" / ".git" / "objects"))

            # Should not ignore regular files
            assert not watcher._is_ignored_path(str(project_root / "test.py"))

    def test_queue_event(self):
        """Test event queuing with debouncing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = IndexWatcher(Path(tmpdir))

            # Queue an event
            event1 = FileChangeEvent(str(Path(tmpdir) / "test.py"), "modified")
            watcher._queue_event(event1)

            assert event1.path in watcher.pending_events
            assert watcher.pending_events[event1.path] == event1

            # Queue another event for same file (should replace)
            event2 = FileChangeEvent(str(Path(tmpdir) / "test.py"), "modified")
            watcher._queue_event(event2)

            assert watcher.pending_events[event1.path] == event2

    def test_process_events_batch(self):
        """Test batch event processing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = IndexWatcher(Path(tmpdir))

            # Set up callback
            processed_events = []
            def callback(events):
                processed_events.extend(events)

            watcher.register_callback(callback)

            # Process batch
            events = [
                FileChangeEvent("file1.py", "created"),
                FileChangeEvent("file2.py", "modified")
            ]
            watcher._process_events_batch(events)

            assert len(processed_events) == 2
            assert processed_events[0].path == "file1.py"
            assert processed_events[1].path == "file2.py"

            # Check stats
            assert watcher.stats['events_processed'] == 2
            assert watcher.stats['files_changed'] == 2