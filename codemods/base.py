"""Base protocol for codemods."""

from abc import ABC, abstractmethod
from typing import Protocol


class CodeMod(Protocol):
    """Protocol for code modification operations."""

    name: str
    description: str

    def preview(self, path: str, text: str) -> str:
        """
        Generate a preview of changes as unified diff.

        Args:
            path: File path being modified
            text: Original file content

        Returns:
            Unified diff string showing changes
        """
        ...

    def apply(self, path: str, text: str) -> str:
        """
        Apply the transformation to the text.

        Args:
            path: File path being modified
            text: Original file content

        Returns:
            Transformed file content
        """
        ...


class BaseCodeMod(ABC):
    """Base class for codemods with common functionality."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def preview(self, path: str, text: str) -> str:
        """Generate preview diff."""
        pass

    @abstractmethod
    def apply(self, path: str, text: str) -> str:
        """Apply transformation."""
        pass

    def _create_unified_diff(self, path: str, original: str, modified: str) -> str:
        """Create unified diff from original and modified text."""
        import difflib

        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm=""
        )
        return "".join(diff)