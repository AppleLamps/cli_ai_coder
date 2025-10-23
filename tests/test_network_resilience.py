"""Tests for network resilience."""

import pytest
from unittest.mock import Mock, patch

from ai.client import XAIClient, CircuitBreaker, CircuitBreakerState


def test_circuit_breaker():
    """Test circuit breaker."""
    breaker = CircuitBreaker(fail_threshold=2, window_sec=10, cooldown_sec=5)

    # Initially closed
    assert breaker.should_attempt()
    assert breaker.get_state() == "closed"

    # Record failures
    breaker.record_failure()
    assert breaker.should_attempt()
    assert breaker.get_state() == "closed"

    breaker.record_failure()
    assert not breaker.should_attempt()
    assert breaker.get_state() == "open"

    # Record success (should not happen when open, but test)
    breaker.record_success()
    assert breaker.get_state() == "closed"


def test_xai_client_offline():
    """Test offline mode."""
    client = XAIClient()
    client.offline_mode = True

    result = client.complete_chat("test-model", [{"role": "user", "content": "test"}])
    assert result == ""  # Should return empty for offline


def test_retry_logic():
    """Test retry logic."""
    client = XAIClient()

    # Mock the client to raise exception
    with patch.object(client.client.chat.completions, 'create', side_effect=Exception("Network error")):
        result = client.complete_chat("test-model", [{"role": "user", "content": "test"}])
        assert result == ""  # Should fail after retries


def test_circuit_breaker_integration():
    """Test circuit breaker in client."""
    client = XAIClient()

    # Mock breaker to be open
    breaker = client._get_circuit_breaker("test-model")
    breaker.state = CircuitBreakerState.OPEN

    result = client.complete_chat("test-model", [{"role": "user", "content": "test"}])
    assert result == ""  # Should fail when breaker open