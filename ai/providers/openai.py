"""OpenAI provider implementation."""

import os
from typing import Dict, List, Optional

from openai import OpenAI

from .base import BaseProvider


class OpenAIProvider(BaseProvider):
    """OpenAI provider."""

    def __init__(self):
        super().__init__("openai")
        self.api_key_env = "OPENAI_API_KEY"
        self.client = None

    def is_available(self) -> bool:
        """Check if OpenAI API key is set."""
        return bool(os.getenv(self.api_key_env))

    def _ensure_client(self):
        """Ensure OpenAI client is initialized."""
        if self.client is None:
            api_key = os.getenv(self.api_key_env)
            if not api_key:
                raise Exception("OPENAI_API_KEY not set")
            self.client = OpenAI(api_key=api_key)

    def _chat_impl(self, messages, model, temperature=0.2, max_tokens=None, stream=False, tools=None, timeout=None):
        """Send chat completion via OpenAI."""
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
            return ""  # Stub
        else:
            return response.choices[0].message.content

    def price_table(self) -> Dict[str, Dict[str, float]]:
        """OpenAI pricing."""
        return {
            "gpt-4": {"input": 30.0, "output": 60.0},
            "gpt-3.5-turbo": {"input": 1.5, "output": 2.0},
        }

    def supports_tools(self) -> bool:
        """OpenAI supports tools."""
        return True