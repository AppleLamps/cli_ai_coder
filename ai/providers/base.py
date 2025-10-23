"""Base provider interface."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Protocol


class Provider(Protocol):
    """Protocol for AI providers."""

    name: str

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        tools: Optional[List[Dict]] = None,
        timeout: Optional[int] = None
    ) -> str:
        """Send chat completion request."""
        ...

    @abstractmethod
    def price_table(self) -> Dict[str, Dict[str, float]]:
        """Return pricing table: {"model": {"input": per_million, "output": per_million}}."""
        ...

    @abstractmethod
    def supports_tools(self) -> bool:
        """Whether this provider supports tool calling."""
        ...


class BaseProvider(ABC):
    """Base provider implementation with common functionality."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available (API key, etc.)."""
        ...

    @abstractmethod
    def _chat_impl(self, messages, model, temperature, max_tokens, stream, tools, timeout) -> str:
        """Implementation-specific chat method."""
        ...

    def chat(self, messages, model, temperature=0.2, max_tokens=None, stream=False, tools=None, timeout=None):
        """Send chat completion, with availability check."""
        if not self.is_available():
            raise Exception(f"Provider {self.name} is not available")
        return self._chat_impl(messages, model, temperature, max_tokens, stream, tools, timeout)