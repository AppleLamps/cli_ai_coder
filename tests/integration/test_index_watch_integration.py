"""Integration tests for file system watcher."""

import os
import tempfile
import time
from pathlib import Path
import pytest

from indexer.watch import IndexWatcher, FileChangeEvent


class TestIndexWatcherIntegration:
    """Integration tests for the watcher."""

    def test_watcher_start_stop(self):
        """Test starting and stopping the watcher."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            watcher = IndexWatcher(project_root)

            # Start watcher
            watcher.start()
            assert watcher.watcher_thread is not None
            assert watcher.processing_thread is not None

            # Stop watcher
            watcher.stop()
            # Threads should be joined

    def test_file_changes_detected(self):
        """Test that file changes are detected (polling mode for test)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            watcher = IndexWatcher(project_root)

            # Override polling interval and debounce for faster, more reliable test
            watcher.polling_interval_ms = 100
            watcher.debounce_ms = 50  # Reduce debounce time for faster event processing

            detected_events = []
            def callback(events):
                detected_events.extend(events)

            watcher.register_callback(callback)

            # Start watcher BEFORE creating file to ensure clean state
            watcher.start()

            try:
                # Give watcher time to initialize and do first poll
                time.sleep(0.15)

                # Create a test file
                test_file = project_root / "test.py"
                test_file.write_text("print('hello')")

                # Wait for polling cycle + debounce + processing buffer
                # polling_interval (100ms) + debounce (50ms) + buffer (100ms) = 250ms
                time.sleep(0.3)

                # Modify file
                test_file.write_text("print('world')")

                # Wait for detection with retry logic
                max_wait = 1.0  # Maximum 1 second wait
                wait_interval = 0.1
                elapsed = 0.0

                while elapsed < max_wait:
                    if len(detected_events) >= 1:
                        break
                    time.sleep(wait_interval)
                    elapsed += wait_interval

                # Should have detected at least one event (creation or modification)
                # In polling mode, we might detect creation and/or modification
                assert len(detected_events) >= 1, (
                    f"Expected at least 1 event, got {len(detected_events)}. "
                    f"Events: {detected_events}"
                )

                # Verify we got a valid event for our test file
                event_paths = [e.path for e in detected_events]
                assert any("test.py" in path for path in event_paths), (
                    f"Expected event for test.py, got events for: {event_paths}"
                )

            finally:
                watcher.stop()