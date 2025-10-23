"""Diagnostics overlay for LSP."""

import threading
from typing import Dict, List, Optional

from prompt_toolkit.formatted_text import FormattedText, StyleAndTextTuples

from language.lsp_client import LSPClient


class DiagnosticItem:
    """Represents a single diagnostic."""

    def __init__(self, range_: Dict, severity: int, message: str, source: str = ""):
        self.range = range_
        self.severity = severity  # 1=Error, 2=Warning, 3=Info, 4=Hint
        self.message = message
        self.source = source

    @property
    def start_line(self) -> int:
        """Get start line (0-indexed)."""
        return self.range["start"]["line"]

    @property
    def end_line(self) -> int:
        """Get end line (0-indexed)."""
        return self.range["end"]["line"]

    @property
    def start_char(self) -> int:
        """Get start character (0-indexed)."""
        return self.range["start"]["character"]

    @property
    def end_char(self) -> int:
        """Get end character (0-indexed)."""
        return self.range["end"]["character"]


class DiagnosticsStore:
    """Thread-safe store for diagnostics per file."""

    def __init__(self):
        self._diagnostics: Dict[str, List[DiagnosticItem]] = {}
        self._lock = threading.RLock()

    def update_diagnostics(self, file_path: str, diagnostics: List[Dict]):
        """Update diagnostics for a file."""
        with self._lock:
            items = []
            for diag in diagnostics:
                item = DiagnosticItem(
                    range_=diag.get("range", {}),
                    severity=diag.get("severity", 1),
                    message=diag.get("message", ""),
                    source=diag.get("source", "")
                )
                items.append(item)
            self._diagnostics[file_path] = items

    def get_diagnostics(self, file_path: str) -> List[DiagnosticItem]:
        """Get diagnostics for a file."""
        with self._lock:
            return self._diagnostics.get(file_path, [])

    def get_line_diagnostics(self, file_path: str, line: int) -> List[DiagnosticItem]:
        """Get diagnostics for a specific line."""
        all_diags = self.get_diagnostics(file_path)
        return [d for d in all_diags if d.start_line <= line <= d.end_line]


class DiagnosticsOverlay:
    """Renders diagnostics as squiggles and provides hover tooltips."""

    SEVERITY_STYLES = {
        1: "underline red",  # Error
        2: "underline yellow",  # Warning
        3: "underline blue",  # Info
        4: "underline cyan"  # Hint
    }

    def __init__(self, diagnostics_store: DiagnosticsStore):
        self.diagnostics_store = diagnostics_store
        self.enabled = True

    def toggle(self):
        """Toggle overlay visibility."""
        self.enabled = not self.enabled

    def apply_to_line(self, file_path: str, line_number: int, line_text: str) -> FormattedText:
        """
        Apply diagnostics styling to a line of text.

        Returns FormattedText with squiggles for diagnostics.
        """
        if not self.enabled:
            return FormattedText([(line_text, "")])

        diagnostics = self.diagnostics_store.get_line_diagnostics(file_path, line_number)
        if not diagnostics:
            return FormattedText([(line_text, "")])

        # Find the most severe diagnostic for this line
        most_severe = min(diagnostics, key=lambda d: d.severity)
        style = self.SEVERITY_STYLES.get(most_severe.severity, "underline")

        # For simplicity, underline the entire line
        # In a real implementation, you'd underline specific character ranges
        return FormattedText([(line_text, style)])

    def get_hover_tooltip(self, file_path: str, line_number: int) -> Optional[str]:
        """
        Get tooltip text for diagnostics on a line.

        Returns the message of the most severe diagnostic, or None if no diagnostics.
        """
        if not self.enabled:
            return None

        diagnostics = self.diagnostics_store.get_line_diagnostics(file_path, line_number)
        if not diagnostics:
            return None

        # Return message of most severe diagnostic
        most_severe = min(diagnostics, key=lambda d: d.severity)
        return f"{most_severe.source}: {most_severe.message}" if most_severe.source else most_severe.message


class LSPDiagnosticsManager:
    """Manages LSP clients and diagnostics for multiple languages."""

    def __init__(self):
        self.clients: Dict[str, LSPClient] = {}
        self.diagnostics_store = DiagnosticsStore()
        self.overlay = DiagnosticsOverlay(self.diagnostics_store)

    def start_language_server(self, language: str) -> bool:
        """Start LSP server for a language."""
        if language in self.clients:
            return True

        client = LSPClient(language)
        client.set_diagnostics_callback(self._on_diagnostics)
        if client.start():
            self.clients[language] = client
            return True
        return False

    def stop_language_server(self, language: str):
        """Stop LSP server for a language."""
        if language in self.clients:
            self.clients[language].stop()
            del self.clients[language]

    def restart_language_server(self, language: str) -> bool:
        """Restart LSP server for a language."""
        self.stop_language_server(language)
        return self.start_language_server(language)

    def notify_file_opened(self, file_path: str, content: str):
        """Notify LSP servers that a file was opened."""
        language = self._detect_language(file_path)
        if language and language in self.clients:
            self.clients[language].did_open(file_path, content)

    def notify_file_changed(self, file_path: str, content: str, version: int = 1):
        """Notify LSP servers that a file changed."""
        language = self._detect_language(file_path)
        if language and language in self.clients:
            self.clients[language].did_change(file_path, content, version)

    def _detect_language(self, file_path: str) -> Optional[str]:
        """Detect language from file extension."""
        if file_path.endswith('.py'):
            return 'python'
        return None

    def _on_diagnostics(self, file_path: str, diagnostics: List[Dict]):
        """Callback for diagnostics updates."""
        self.diagnostics_store.update_diagnostics(file_path, diagnostics)

    def shutdown(self):
        """Shutdown all LSP clients."""
        for client in self.clients.values():
            client.stop()
        self.clients.clear()