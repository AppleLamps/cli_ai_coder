"""File system watcher for incremental index updates."""

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from queue import Queue, Empty
import fnmatch

from core.config import get_config

logger = logging.getLogger(__name__)


class FileChangeEvent:
    """Represents a file system change event."""

    def __init__(self, path: str, event_type: str, is_dir: bool = False):
        self.path = path
        self.event_type = event_type  # 'created', 'modified', 'deleted', 'moved'
        self.is_dir = is_dir
        self.timestamp = time.time()

    def __repr__(self):
        return f"FileChangeEvent({self.event_type}, {self.path})"


class IndexWatcher:
    """File system watcher for incremental index updates."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config = get_config()
        self.enabled = self.config.index_enabled and getattr(self.config, 'index_watch_enabled', True)
        self.debounce_ms = getattr(self.config, 'index_watch_debounce_ms', 300)
        self.polling_fallback = getattr(self.config, 'index_watch_polling_fallback', True)
        self.polling_interval_ms = getattr(self.config, 'index_watch_polling_interval_ms', 1500)

        self.ignored_globs = getattr(self.config, 'index_ignored_globs', [
            '**/.git/**', '**/.cli_ai_coder/**', '**/__pycache__/**',
            '**/*.pyc', '**/*.pyo', '**/.pytest_cache/**'
        ])

        self.event_queue: Queue[FileChangeEvent] = Queue()
        self.last_event_times: Dict[str, float] = {}
        self.pending_events: Dict[str, FileChangeEvent] = {}

        self.watcher_thread: Optional[threading.Thread] = None
        self.processing_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

        self.callbacks: List[Callable[[List[FileChangeEvent]], None]] = []

        # Stats
        self.stats = {
            'events_processed': 0,
            'files_changed': 0,
            'last_update': 0.0,
            'backend': 'none'
        }

    def register_callback(self, callback: Callable[[List[FileChangeEvent]], None]):
        """Register a callback for batched file change events."""
        self.callbacks.append(callback)

    def start(self):
        """Start the file system watcher."""
        if not self.enabled:
            logger.info("Index watcher disabled")
            return

        logger.info("Starting index watcher")
        self.stop_event.clear()

        # Start processing thread
        self.processing_thread = threading.Thread(
            target=self._process_events_loop,
            daemon=True,
            name="IndexWatcher-Processor"
        )
        self.processing_thread.start()

        # Try to start FS watcher, fallback to polling
        if self._start_fs_watcher():
            self.stats['backend'] = 'watchdog'
        elif self.polling_fallback:
            self._start_polling_watcher()
            self.stats['backend'] = 'polling'
        else:
            logger.warning("No file system watcher available and polling disabled")
            return

        logger.info(f"Index watcher started with backend: {self.stats['backend']}")

    def stop(self):
        """Stop the file system watcher."""
        if not self.enabled:
            return

        logger.info("Stopping index watcher")
        self.stop_event.set()

        if self.watcher_thread and self.watcher_thread.is_alive():
            self.watcher_thread.join(timeout=5.0)

        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5.0)

        logger.info("Index watcher stopped")

    def _start_fs_watcher(self) -> bool:
        """Try to start watchdog-based file system watcher."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class WatcherHandler(FileSystemEventHandler):
                def __init__(self, watcher: 'IndexWatcher'):
                    self.watcher = watcher

                def on_created(self, event):
                    if not event.is_directory:
                        self.watcher._queue_event(FileChangeEvent(
                            event.src_path, 'created', event.is_directory
                        ))

                def on_modified(self, event):
                    if not event.is_directory:
                        self.watcher._queue_event(FileChangeEvent(
                            event.src_path, 'modified', event.is_directory
                        ))

                def on_deleted(self, event):
                    if not event.is_directory:
                        self.watcher._queue_event(FileChangeEvent(
                            event.src_path, 'deleted', event.is_directory
                        ))

                def on_moved(self, event):
                    if not event.is_directory:
                        # Queue delete for old path and create for new path
                        self.watcher._queue_event(FileChangeEvent(
                            event.src_path, 'deleted', event.is_directory
                        ))
                        self.watcher._queue_event(FileChangeEvent(
                            event.dest_path, 'created', event.is_directory
                        ))

            observer = Observer()
            handler = WatcherHandler(self)
            observer.schedule(handler, str(self.project_root), recursive=True)
            observer.start()

            self.watcher_thread = threading.Thread(
                target=lambda: observer.join(),
                daemon=True,
                name="IndexWatcher-Watchdog"
            )
            self.watcher_thread.start()

            return True

        except ImportError:
            logger.info("watchdog not available, trying polling fallback")
            return False
        except Exception as e:
            logger.warning(f"Failed to start watchdog watcher: {e}")
            return False

    def _start_polling_watcher(self):
        """Start polling-based file system watcher."""
        logger.info(f"Starting polling watcher with {self.polling_interval_ms}ms interval")

        def poll_loop():
            last_mtimes: Dict[str, float] = {}
            known_files: Set[str] = set()

            while not self.stop_event.is_set():
                try:
                    current_files = set()
                    current_mtimes = {}

                    # Walk directory tree
                    for root, dirs, files in Path(self.project_root).walk():
                        # Skip ignored dirs
                        dirs[:] = [d for d in dirs if not self._is_ignored_dir(d)]

                        for file in files:
                            if self._should_watch_file(file):
                                file_path = root / file
                                rel_path = str(file_path.relative_to(self.project_root))

                                current_files.add(rel_path)
                                current_mtimes[rel_path] = file_path.stat().st_mtime

                    # Detect changes
                    new_files = current_files - known_files
                    deleted_files = known_files - current_files
                    modified_files = set()

                    for rel_path in current_files & known_files:
                        if current_mtimes.get(rel_path) != last_mtimes.get(rel_path):
                            modified_files.add(rel_path)

                    # Queue events
                    for rel_path in new_files:
                        self._queue_event(FileChangeEvent(rel_path, 'created'))
                    for rel_path in modified_files:
                        self._queue_event(FileChangeEvent(rel_path, 'modified'))
                    for rel_path in deleted_files:
                        self._queue_event(FileChangeEvent(rel_path, 'deleted'))

                    # Update state
                    known_files = current_files
                    last_mtimes = current_mtimes

                except Exception as e:
                    logger.warning(f"Polling watcher error: {e}")

                # Wait for next poll
                self.stop_event.wait(self.polling_interval_ms / 1000.0)

        self.watcher_thread = threading.Thread(
            target=poll_loop,
            daemon=True,
            name="IndexWatcher-Polling"
        )
        self.watcher_thread.start()

    def _queue_event(self, event: FileChangeEvent):
        """Queue a file change event with debouncing."""
        if self._is_ignored_path(event.path):
            return

        # Debounce: replace pending event for same path
        self.pending_events[event.path] = event
        self.last_event_times[event.path] = event.timestamp

    def _process_events_loop(self):
        """Process queued events in batches."""
        while not self.stop_event.is_set():
            try:
                # Wait for events or timeout
                events = []
                try:
                    # Get first event (blocking)
                    first_event = self.event_queue.get(timeout=1.0)
                    events.append(first_event)

                    # Get any additional events (non-blocking)
                    while True:
                        try:
                            event = self.event_queue.get_nowait()
                            events.append(event)
                        except Empty:
                            break

                except Empty:
                    # Check for debounced events
                    now = time.time()
                    expired_events = []

                    for path, event in list(self.pending_events.items()):
                        if now - event.timestamp >= (self.debounce_ms / 1000.0):
                            expired_events.append(event)
                            del self.pending_events[path]

                    if expired_events:
                        events.extend(expired_events)

                if events:
                    self._process_events_batch(events)

            except Exception as e:
                logger.error(f"Event processing error: {e}")

    def _process_events_batch(self, events: List[FileChangeEvent]):
        """Process a batch of file change events."""
        if not events:
            return

        # Deduplicate events (keep latest per path)
        latest_events = {}
        for event in events:
            latest_events[event.path] = event

        batched_events = list(latest_events.values())

        # Update stats
        self.stats['events_processed'] += len(batched_events)
        self.stats['files_changed'] = len(latest_events)
        self.stats['last_update'] = time.time()

        # Call registered callbacks
        for callback in self.callbacks:
            try:
                callback(batched_events)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _should_watch_file(self, filename: str) -> bool:
        """Check if file should be watched."""
        # Skip binary files and common non-text extensions
        binary_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg',
                       '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                       '.zip', '.tar', '.gz', '.bz2', '.7z', '.exe', '.dll', '.so',
                       '.dylib', '.pyc', '.pyo', '.class', '.jar', '.bin'}

        if any(filename.endswith(ext) for ext in binary_exts):
            return False

        # Check ignored globs
        for pattern in self.ignored_globs:
            if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch('**/' + filename, pattern):
                return False

        return True

    def _is_ignored_dir(self, dirname: str) -> bool:
        """Check if directory should be ignored."""
        dirname = dirname.replace('\\', '/')
        for pattern in self.ignored_globs:
            if Path(dirname).match(pattern):
                return True
        return False

    def _is_ignored_path(self, path: str) -> bool:
        """Check if path should be ignored."""
        try:
            rel_path = Path(path).relative_to(self.project_root)
            path_str = str(rel_path).replace('\\', '/')

            # Check for .git in path
            if '.git' in path_str.split('/'):
                return True

            for pattern in self.ignored_globs:
                if Path(path_str).match(pattern):
                    return True

            # Also check filename
            filename = Path(path).name
            return not self._should_watch_file(filename)

        except ValueError:
            # Path not under project root
            return True

    def get_stats(self) -> Dict:
        """Get watcher statistics."""
        return dict(self.stats)


# Global watcher instance
_watcher: Optional[IndexWatcher] = None


def get_watcher(project_root: Path) -> IndexWatcher:
    """Get or create the global index watcher."""
    global _watcher
    if _watcher is None:
        _watcher = IndexWatcher(project_root)
    return _watcher


def start_watching(project_root: Path):
    """Start watching for file changes."""
    watcher = get_watcher(project_root)
    watcher.start()


def stop_watching():
    """Stop watching for file changes."""
    global _watcher
    if _watcher:
        _watcher.stop()
        _watcher = None
