"""Example plugin demonstrating the plugin system."""

from typing import Dict, List
from plugins import ProviderPlugin


class ExampleProvider(ProviderPlugin):
    """Example AI provider plugin."""

    @property
    def name(self) -> str:
        return "example_provider"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Example provider plugin for demonstration"

    @property
    def author(self) -> str:
        return "CLI AI Coder Team"

    def get_models(self) -> List[str]:
        """Return supported models."""
        return ["example-gpt", "example-claude"]

    def complete_chat(self, model: str, messages: List[Dict], **kwargs) -> str:
        """Complete a chat conversation."""
        if model not in self.get_models():
            raise ValueError(f"Unsupported model: {model}")

        # Simple mock response
        last_message = messages[-1]["content"] if messages else "Hello"
        return f"Example response to: {last_message}"

    def check_available(self) -> bool:
        """Check if provider is available."""
        return True  # Always available for demo