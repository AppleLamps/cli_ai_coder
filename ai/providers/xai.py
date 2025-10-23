"""xAI provider implementation."""

import os
from typing import Dict, List, Optional

from openai import OpenAI

from .base import BaseProvider


class XAIProvider(BaseProvider):
    """xAI provider using OpenAI SDK."""

    def __init__(self):
        super().__init__("xai")
        self.api_key_env = "XAI_API_KEY"
        self.client = None

    def is_available(self) -> bool:
        """Check if xAI API key is set."""
        return bool(os.getenv(self.api_key_env))

    def _ensure_client(self):
        """Ensure OpenAI client is initialized."""
        if self.client is None:
            api_key = os.getenv(self.api_key_env)
            if not api_key:
                raise Exception("XAI_API_KEY not set")
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.x.ai/v1"
            )

    def _chat_impl(self, messages, model, temperature=0.2, max_tokens=None, stream=False, tools=None, timeout=None):
        """Send chat completion via xAI."""
        self._ensure_client()
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            tools=tools,
            timeout=timeout
        )
        if stream:
            # For streaming, return the stream object or handle differently
            # For now, assume non-streaming
            return response.choices[0].message.content
        else:
            return response.choices[0].message.content

    def price_table(self) -> Dict[str, Dict[str, float]]:
        """xAI pricing (placeholder - update with real prices)."""
        return {
            "grok-code-fast-1": {"input": 0.0, "output": 0.0},  # Free for now?
        }

    def supports_tools(self) -> bool:
        """xAI supports tools."""
        return True