"""Utility functions."""

import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, List


@dataclass
class CompletionMetrics:
    """Metrics for a single AI completion."""
    model: str
    input_tokens: int
    output_tokens: int
    elapsed_ms: int
    timestamp: float


class MetricsStore:
    """Thread-safe store for AI completion metrics."""

    def __init__(self, max_entries: int = 10):
        self.max_entries = max_entries
        self.metrics: Deque[CompletionMetrics] = deque(maxlen=max_entries)

    def add_completion(self, model: str, input_tokens: int, output_tokens: int, elapsed_ms: int):
        """Add a completion metric."""
        metric = CompletionMetrics(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            elapsed_ms=elapsed_ms,
            timestamp=time.time()
        )
        self.metrics.append(metric)

    def get_recent(self, count: int = 5) -> List[CompletionMetrics]:
        """Get the most recent metrics."""
        return list(self.metrics)[-count:]

    def get_latest(self) -> CompletionMetrics | None:
        """Get the latest metric."""
        return self.metrics[-1] if self.metrics else None


def redact(text: str, patterns: List[str]) -> str:
    """
    Redact sensitive patterns from text.

    Args:
        text: The text to redact.
        patterns: List of patterns to redact (case-insensitive).

    Returns:
        Redacted text with patterns replaced by '[REDACTED]'.
    """
    result = text
    for pattern in patterns:
        # Use word boundaries and case-insensitive matching
        regex = re.compile(r'\b' + re.escape(pattern) + r'\b', re.IGNORECASE)
        result = regex.sub('[REDACTED]', result)
    return result