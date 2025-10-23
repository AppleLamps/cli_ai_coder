"""Tests for LSP diagnostics."""

import json
import pytest
from unittest.mock import Mock, patch

from language.lsp_client import LSPClient


class MockLSPProcess:
    """Mock LSP process for testing."""

    def __init__(self, responses):
        self.responses = responses
        self.stdin = Mock()
        self.stdout = Mock()
        self.stderr = Mock()
        self.sent_messages = []

    def send_message(self, message):
        """Send a message to the mock."""
        self.sent_messages.append(message)

    def terminate(self):
        pass

    def wait(self, timeout=None):
        pass


def test_lsp_client_initialization():
    """Test LSP client initialization."""
    client = LSPClient("python")
    assert client.language == "python"
    assert not client.running


def test_lsp_diagnostics_store():
    """Test diagnostics store."""
    from editor.diagnostics import DiagnosticsStore, DiagnosticItem

    store = DiagnosticsStore()
    diagnostics = [
        {
            "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 10}},
            "severity": 1,
            "message": "Syntax error",
            "source": "pylsp"
        }
    ]

    store.update_diagnostics("test.py", diagnostics)
    items = store.get_diagnostics("test.py")
    assert len(items) == 1
    assert items[0].severity == 1
    assert items[0].message == "Syntax error"


def test_diagnostics_overlay():
    """Test diagnostics overlay."""
    from editor.diagnostics import DiagnosticsStore, DiagnosticsOverlay

    store = DiagnosticsStore()
    overlay = DiagnosticsOverlay(store)

    # Test toggle
    assert overlay.enabled
    overlay.toggle()
    assert not overlay.enabled
    overlay.toggle()  # Toggle back on for styling test
    assert overlay.enabled

    # Test line styling
    diagnostics = [
        {
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 10}},
            "severity": 1,
            "message": "Error",
            "source": "test"
        }
    ]
    store.update_diagnostics("test.py", diagnostics)

    styled = overlay.apply_to_line("test.py", 0, "print('hello')")
    # Should have underline red style
    assert "underline red" in str(styled)

    # Test hover
    tooltip = overlay.get_hover_tooltip("test.py", 0)
    assert tooltip is not None and "Error" in tooltip


def test_lsp_diagnostics_manager():
    """Test LSP diagnostics manager."""
    from editor.diagnostics import LSPDiagnosticsManager

    manager = LSPDiagnosticsManager()

    # Test start server (will fail without pylsp, but should not crash)
    success = manager.start_language_server("python")
    # In test environment, likely False
    assert isinstance(success, bool)

    manager.shutdown()