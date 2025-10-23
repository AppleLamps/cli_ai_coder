"""Tests for tool-calling loop."""

import pytest
from unittest.mock import Mock, patch

from ai.client import XAIClient


def test_tool_loop_single_call():
    """Test tool loop with single tool call."""
    client = XAIClient()

    # Register a mock tool
    def mock_repo_search(query):
        return {"results": ["file1.py", "file2.py"]}

    client.register_tool("repo_search", mock_repo_search)

    # Mock the API response with tool call
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.tool_calls = [
        Mock(id="call1", function=Mock(name="repo_search", arguments='{"query": "test"}'))
    ]
    mock_response.choices[0].message.content = None

    # Mock the final response
    mock_final = Mock()
    mock_final.choices = [Mock()]
    mock_final.choices[0].message = Mock()
    mock_final.choices[0].message.content = "Final answer"
    mock_final.choices[0].message.tool_calls = None

    with patch.object(client.client.chat.completions, 'create', side_effect=[mock_response, mock_final]):

        messages = [{"role": "user", "content": "Test prompt"}]
        result = client.complete_chat("test-model", messages, enable_tools=True)

        assert "Final answer" in result


def test_tool_loop_multiple_calls():
    """Test tool loop with multiple tool calls."""
    client = XAIClient()

    # Register mock tools
    def mock_repo_search(query):
        return {"results": ["file1.py"]}

    def mock_read_file(path):
        return {"content": "file content"}

    client.register_tool("repo_search", mock_repo_search)
    client.register_tool("read_file", mock_read_file)

    # First response with tool call
    mock_response1 = Mock()
    mock_response1.choices = [Mock()]
    mock_response1.choices[0].message = Mock()
    mock_response1.choices[0].message.tool_calls = [
        Mock(id="call1", function=Mock(name="repo_search", arguments='{"query": "test"}'))
    ]
    mock_response1.choices[0].message.content = None

    # Second response with another tool call
    mock_response2 = Mock()
    mock_response2.choices = [Mock()]
    mock_response2.choices[0].message = Mock()
    mock_response2.choices[0].message.tool_calls = [
        Mock(id="call2", function=Mock(name="read_file", arguments='{"path": "file1.py"}'))
    ]
    mock_response2.choices[0].message.content = None

    # Final response
    mock_final = Mock()
    mock_final.choices = [Mock()]
    mock_final.choices[0].message = Mock()
    mock_final.choices[0].message.content = "Final answer"
    mock_final.choices[0].message.tool_calls = None

    with patch.object(client.client.chat.completions, 'create', side_effect=[mock_response1, mock_response2, mock_final]):

        messages = [{"role": "user", "content": "Test prompt"}]
        result = client.complete_chat("test-model", messages, enable_tools=True)

        assert "Final answer" in result


def test_tool_loop_max_iterations():
    """Test tool loop respects max iterations."""
    client = XAIClient()

    # Register a mock tool
    def mock_repo_search(query):
        return {"results": []}

    client.register_tool("repo_search", mock_repo_search)

    # Always return tool calls
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.tool_calls = [
        Mock(id="call1", function=Mock(name="repo_search", arguments='{"query": "test"}'))
    ]
    mock_response.choices[0].message.content = None

    with patch.object(client.client.chat.completions, 'create', return_value=mock_response):

        messages = [{"role": "user", "content": "Test prompt"}]
        result = client.complete_chat("test-model", messages, enable_tools=True)

        # Should hit max iterations and return empty (no final content)
        assert result == ""