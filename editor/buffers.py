"""Multi-buffer and tab management."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class BufferState:
    """State of a buffer."""
    path: Optional[Path]
    text: str
    dirty: bool = False


class BufferManager:
    """Manages multiple text buffers."""

    def __init__(self) -> None:
        self.buffers: Dict[Optional[str], BufferState] = {}
        self.active_key: Optional[str] = None

    def open(self, path: Path) -> str:
        """
        Open a file in a new buffer.

        Args:
            path: Path to the file.

        Returns:
            Buffer key.
        """
        key = str(path)
        if key not in self.buffers:
            try:
                text = path.read_text(encoding='utf-8')
            except FileNotFoundError:
                text = ""
            self.buffers[key] = BufferState(path=path, text=text)
        self.active_key = key
        return key

    def get(self, key: str) -> Optional[BufferState]:
        """
        Get a buffer by key.

        Args:
            key: Buffer key.

        Returns:
            Buffer state or None if not found.
        """
        return self.buffers.get(key)

    def list(self) -> List[str]:
        """
        List all buffer keys.

        Returns:
            List of buffer keys.
        """
        return list(self.buffers.keys())

    def active(self) -> Optional[BufferState]:
        """
        Get the active buffer.

        Returns:
            Active buffer state or None.
        """
        if self.active_key:
            return self.buffers.get(self.active_key)
        return None

    def activate(self, key: str) -> None:
        """
        Activate a buffer.

        Args:
            key: Buffer key to activate.
        """
        if key in self.buffers:
            self.active_key = key

    def update_text(self, key: str, text: str) -> None:
        """
        Update the text of a buffer.

        Args:
            key: Buffer key.
            text: New text content.
        """
        if key in self.buffers:
            self.buffers[key].text = text
            self.buffers[key].dirty = True