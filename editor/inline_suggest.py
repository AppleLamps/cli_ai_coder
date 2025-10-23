"""Inline AI suggestions (ghost text)."""

import asyncio
import time
from typing import Optional

from core.config import get_config


class InlineSuggest:
    """Manages inline AI suggestions."""

    def __init__(self):
        self.config = get_config()
        self.last_suggestion_time = 0
        self.current_suggestion = None
        self.suggestion_task = None

    def should_trigger(self, current_line: str, cursor_pos: int) -> bool:
        """Check if we should trigger inline suggestion."""
        if not self.config.inline_suggest_enabled:
            return False

        # Check idle time
        now = time.time()
        if now - self.last_suggestion_time < self.config.inline_suggest_idle_ms / 1000:
            return False

        # Check if in code context (not empty line, not comment, etc.)
        line = current_line[:cursor_pos].strip()
        if not line or line.startswith('#') or line.startswith('//'):
            return False

        return True

    def trigger_suggestion(self, current_line: str, cursor_pos: int, language: str = "python") -> Optional[str]:
        """Trigger inline suggestion."""
        if not self.should_trigger(current_line, cursor_pos):
            return None

        # Cancel existing task
        if self.suggestion_task and not self.suggestion_task.done():
            self.suggestion_task.cancel()

        # Start new task
        self.suggestion_task = asyncio.create_task(self._generate_suggestion(current_line, cursor_pos, language))
        self.last_suggestion_time = time.time()

        # For now, return a placeholder - in real implementation, this would be async
        return None

    async def _generate_suggestion(self, current_line: str, cursor_pos: int, language: str) -> Optional[str]:
        """Generate suggestion using AI."""
        try:
            from ai.client import XAIClient
            client = XAIClient()

            # Build prompt
            prefix = current_line[:cursor_pos]
            prompt = f"Complete this {language} code:\n{prefix}"

            messages = [{"role": "user", "content": prompt}]

            # Get suggestion
            response = client.complete_chat(
                model=self.config.inline_suggest_model,
                messages=messages,
                temperature=0.1,
                max_tokens=self.config.inline_suggest_max_chars,
                stream=False
            )

            if response and len(response) <= self.config.inline_suggest_max_chars:
                self.current_suggestion = response.strip()
                return self.current_suggestion

        except Exception:
            # Silently fail
            pass

        return None

    def accept_suggestion(self) -> Optional[str]:
        """Accept current suggestion."""
        suggestion = self.current_suggestion
        self.current_suggestion = None
        return suggestion

    def dismiss_suggestion(self):
        """Dismiss current suggestion."""
        self.current_suggestion = None

    def get_current_suggestion(self) -> Optional[str]:
        """Get current suggestion."""
        return self.current_suggestion


# Global instance
inline_suggest = InlineSuggest()