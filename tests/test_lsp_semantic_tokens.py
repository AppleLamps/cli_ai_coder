"""Tests for LSP semantic tokens."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from editor.semantics import SemanticTokenRenderer, SemanticTokensManager
from language.lsp_client import LSPClient


class TestSemanticTokenRenderer:
    """Test semantic token rendering."""

    def test_render_tokens_empty(self):
        """Test rendering with no tokens."""
        renderer = SemanticTokenRenderer()
        text = "print('hello')"
        result = renderer.render_tokens(text, [])
        # FormattedText is a wrapper, we can't easily test internals
        assert result is not None

    def test_render_tokens_simple(self):
        """Test rendering with simple tokens."""
        renderer = SemanticTokenRenderer()
        text = "def func():\n    pass"
        tokens = [
            {"line": 0, "start": 0, "length": 3, "type": "keyword", "modifiers": []},
            {"line": 0, "start": 4, "length": 4, "type": "function", "modifiers": ["definition"]},
        ]
        result = renderer.render_tokens(text, tokens)

        # Just check that it returns a FormattedText object
        assert result is not None

    def test_get_token_style(self):
        """Test token style generation."""
        renderer = SemanticTokenRenderer()

        # Test basic style
        style = renderer._get_token_style("function", [])
        assert "fg:#DCDCAA" in style

        # Test with modifiers
        style = renderer._get_token_style("function", ["definition"])
        assert "fg:#DCDCAA" in style
        assert "underline" in style

        # Test unknown type
        style = renderer._get_token_style("unknown", [])
        assert style == ""


class TestSemanticTokensManager:
    """Test semantic tokens manager."""

    def test_update_and_get(self):
        """Test updating and retrieving tokens."""
        manager = SemanticTokensManager()
        file_path = "test.py"
        tokens = [{"line": 0, "start": 0, "length": 3, "type": "keyword", "modifiers": []}]

        manager.update_tokens(file_path, tokens)
        text = "def func():"
        result = manager.get_rendered_text(file_path, text)

        assert result is not None

    def test_clear_cache(self):
        """Test clearing token cache."""
        manager = SemanticTokensManager()
        file_path = "test.py"
        tokens = [{"line": 0, "start": 0, "length": 3, "type": "keyword", "modifiers": []}]

        manager.update_tokens(file_path, tokens)
        assert file_path in manager.tokens_cache

        manager.clear_cache(file_path)
        assert file_path not in manager.tokens_cache

        manager.clear_cache()  # Clear all
        assert len(manager.tokens_cache) == 0


class TestLSPClientSemanticTokens:
    """Test LSP client semantic tokens functionality."""

    @pytest.mark.asyncio
    async def test_semantic_tokens_full(self):
        """Test requesting semantic tokens."""
        from editor.lsp_actions import LSPActionHandler
        
        handler = LSPActionHandler(None, None)
        client = LSPClient("python")
        client.running = True
        client._send_request_async = AsyncMock()
        handler.register_client("python", client)

        # Mock response
        mock_response = {
            "data": [0, 0, 3, 15, 0, 0, 4, 4, 12, 2]  # def (keyword), func (function+definition)
        }
        client._send_request_async.return_value = mock_response

        result = await handler.semantic_tokens_full("test.py")

        assert result is not None
        assert len(result) == 2
        assert result[0]["type"] == "keyword"
        assert result[1]["type"] == "function"
        assert result[1]["modifiers"] == ["definition"]

    @pytest.mark.asyncio
    async def test_code_action(self):
        """Test requesting code actions."""
        client = LSPClient("python")
        client.running = True
        client._send_request_async = AsyncMock()

        # Mock response with organize imports action
        mock_response = [
            {
                "title": "Organize Imports",
                "command": "python.organizeImports",
                "arguments": ["test.py"]
            }
        ]
        client._send_request_async.return_value = mock_response

        result = await client.code_action("test.py", 0, 0, 10, 0)

        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "Organize Imports"

    @pytest.mark.asyncio
    async def test_execute_command(self):
        """Test executing workspace command."""
        client = LSPClient("python")
        client.running = True
        client._send_request_async = AsyncMock()

        mock_response = {"applied": True}
        client._send_request_async.return_value = mock_response

        result = await client.execute_command("python.organizeImports", ["test.py"])

        assert result == mock_response