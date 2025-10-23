"""Ollama provider implementation."""

import os
from typing import Dict, List, Optional

from .base import BaseProvider


class OllamaProvider(BaseProvider):
    """Ollama local provider."""

    def __init__(self):
        super().__init__("ollama")
        self.base_url = "http://localhost:11434"

    def is_available(self) -> bool:
        """Check if Ollama is running."""
        # Stub - check if server responds
        return False  # Not implemented yet

    def _chat_impl(self, messages, model, temperature=0.2, max_tokens=None, stream=False, tools=None, timeout=None):
        """Send chat completion via Ollama."""
        # Stub implementation
        raise NotImplementedError("Ollama provider not implemented yet")

    def price_table(self) -> Dict[str, Dict[str, float]]:
        """Ollama is free."""
        return {}  # Free

    def supports_tools(self) -> bool:
        """Ollama may support tools in future."""
        return False