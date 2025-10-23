"""Tests for tool redaction utilities."""

import pytest
from core.utils import redact


DEFAULT_PATTERNS = ["API_KEY", "SECRET", "TOKEN", "PASSWORD"]


def test_redact_basic():
    """Test basic redaction."""
    text = "API key: API_KEY"
    result = redact(text, DEFAULT_PATTERNS)
    assert "API_KEY" not in result
    assert "[REDACTED]" in result


def test_redact_multiple_patterns():
    """Test redaction of multiple sensitive patterns."""
    text = "API_KEY: sk-123, SECRET: abc123, TOKEN: xyz789"
    result = redact(text, DEFAULT_PATTERNS)
    assert "API_KEY" not in result
    assert "SECRET" not in result
    assert "TOKEN" not in result
    assert result.count("[REDACTED]") == 3


def test_redact_no_sensitive_data():
    """Test redaction when no sensitive data is present."""
    text = "This is normal text without secrets."
    result = redact(text, DEFAULT_PATTERNS)
    assert result == text


def test_redact_partial_matches():
    """Test that partial matches are not redacted."""
    text = "This mentions 'api key' but no actual key."
    result = redact(text, DEFAULT_PATTERNS)
    assert result == text