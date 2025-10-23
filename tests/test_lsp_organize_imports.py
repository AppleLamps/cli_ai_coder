"""Tests for LSP organize imports."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from editor.lsp_actions import LSPActionHandler
from language.lsp_client import LSPClient


class TestLSPOrganizeImports:
    """Test LSP organize imports functionality."""

    @pytest.fixture
    def lsp_handler(self):
        """Create LSP handler for testing."""
        return LSPActionHandler(None, None)

    @pytest.fixture
    def mock_client(self):
        """Create mock LSP client."""
        client = MagicMock(spec=LSPClient)
        client.code_action = AsyncMock()
        client.execute_command = AsyncMock()
        return client

    def test_organize_imports_no_client(self, lsp_handler):
        """Test organize imports with no client."""
        import asyncio
        result = asyncio.run(lsp_handler.organize_imports("test.py"))
        assert result is None

    def test_organize_imports_with_client(self, lsp_handler, mock_client):
        """Test organize imports with client."""
        lsp_handler.lsp_clients["python"] = mock_client

        # Mock code action response
        mock_client.code_action.return_value = [
            {
                "title": "Organize Imports",
                "command": "python.organizeImports",
                "arguments": ["test.py"]
            }
        ]
        mock_client.execute_command.return_value = {"applied": True}

        import asyncio
        result = asyncio.run(lsp_handler.organize_imports("test.py"))

        assert result == {"applied": True}
        mock_client.code_action.assert_called_once()
        mock_client.execute_command.assert_called_once_with("python.organizeImports", ["test.py"])

    def test_organize_imports_no_action(self, lsp_handler, mock_client):
        """Test organize imports when no action is available."""
        lsp_handler.lsp_clients["python"] = mock_client

        # Mock empty code action response
        mock_client.code_action.return_value = []

        import asyncio
        result = asyncio.run(lsp_handler.organize_imports("test.py"))

        assert result is None
        mock_client.code_action.assert_called_once()
        mock_client.execute_command.assert_not_called()

    def test_organize_imports_with_edit(self, lsp_handler, mock_client):
        """Test organize imports with direct edit."""
        lsp_handler.lsp_clients["python"] = mock_client

        # Mock code action with edit
        mock_client.code_action.return_value = [
            {
                "title": "Organize Imports",
                "edit": {
                    "changes": {
                        "file://test.py": [
                            {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 1, "character": 0}}, "newText": ""}
                        ]
                    }
                }
            }
        ]

        import asyncio
        result = asyncio.run(lsp_handler.organize_imports("test.py"))

        assert result is not None
        assert len(result) == 1
        mock_client.code_action.assert_called_once()
        mock_client.execute_command.assert_not_called()

    def test_decode_semantic_tokens(self, lsp_handler):
        """Test decoding semantic token data."""
        # Sample data: [delta_line, delta_start, length, token_type, token_modifiers]
        data = [0, 0, 3, 15, 0, 0, 4, 4, 12, 2]  # def (keyword), func (function+definition)

        tokens = lsp_handler._decode_semantic_tokens(data)

        assert len(tokens) == 2

        # First token: def
        assert tokens[0]["line"] == 0
        assert tokens[0]["start"] == 0
        assert tokens[0]["length"] == 3
        assert tokens[0]["type"] == "keyword"
        assert tokens[0]["modifiers"] == []

        # Second token: func
        assert tokens[1]["line"] == 0
        assert tokens[1]["start"] == 4
        assert tokens[1]["length"] == 4
        assert tokens[1]["type"] == "function"
        assert tokens[1]["modifiers"] == ["definition"]

    def test_decode_semantic_tokens_incomplete(self, lsp_handler):
        """Test decoding with incomplete data."""
        data = [0, 0, 3, 15]  # Incomplete token (missing modifier)

        tokens = lsp_handler._decode_semantic_tokens(data)

        assert len(tokens) == 0  # No complete tokens