"""Tests for LSP actions."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from editor.lsp_actions import LSPActionHandler
from editor.buffers import BufferManager
from editor.statusbar import StatusBar


@pytest.fixture
def buffer_manager():
    """Create a mock buffer manager."""
    return MagicMock(spec=BufferManager)


@pytest.fixture
def status_bar():
    """Create a mock status bar."""
    return MagicMock(spec=StatusBar)


@pytest.fixture
def lsp_handler(buffer_manager, status_bar):
    """Create LSP action handler."""
    handler = LSPActionHandler(buffer_manager, status_bar)
    return handler


@pytest.fixture
def mock_lsp_client():
    """Create a mock LSP client."""
    client = MagicMock()
    client.hover = AsyncMock()
    client.definition = AsyncMock()
    client.references = AsyncMock()
    client.rename = AsyncMock()
    client.formatting = AsyncMock()
    return client


class TestLSPActionHandler:
    """Test LSP action handler."""

    def test_init(self, lsp_handler, buffer_manager, status_bar):
        """Test initialization."""
        assert lsp_handler.buffer_manager == buffer_manager
        assert lsp_handler.status_bar == status_bar
        assert lsp_handler.lsp_clients == {}

    def test_register_client(self, lsp_handler, mock_lsp_client):
        """Test registering LSP client."""
        lsp_handler.register_client("python", mock_lsp_client)
        assert lsp_handler.lsp_clients["python"] == mock_lsp_client

    def test_get_client(self, lsp_handler, mock_lsp_client):
        """Test getting LSP client."""
        lsp_handler.register_client("python", mock_lsp_client)
        assert lsp_handler.get_client("python") == mock_lsp_client
        assert lsp_handler.get_client("unknown") is None

    @pytest.mark.asyncio
    async def test_hover_success(self, lsp_handler, mock_lsp_client):
        """Test successful hover request."""
        lsp_handler.register_client("python", mock_lsp_client)
        mock_lsp_client.hover.return_value = {"contents": {"value": "test hover"}}

        result = await lsp_handler.hover("test.py", 1, 5)
        assert result == "test hover"
        mock_lsp_client.hover.assert_called_once_with("test.py", 1, 5)

    @pytest.mark.asyncio
    async def test_hover_no_client(self, lsp_handler):
        """Test hover with no client."""
        result = await lsp_handler.hover("test.py", 1, 5)
        assert result is None

    @pytest.mark.asyncio
    async def test_hover_error(self, lsp_handler, mock_lsp_client, status_bar):
        """Test hover with error."""
        lsp_handler.register_client("python", mock_lsp_client)
        mock_lsp_client.hover.side_effect = Exception("Test error")

        result = await lsp_handler.hover("test.py", 1, 5)
        assert result is None
        status_bar.set_message.assert_called_once_with("Hover error: Test error")

    @pytest.mark.asyncio
    async def test_definition_success(self, lsp_handler, mock_lsp_client):
        """Test successful definition request."""
        lsp_handler.register_client("python", mock_lsp_client)
        mock_lsp_client.definition.return_value = [{
            "uri": "file:///test.py",
            "range": {"start": {"line": 10, "character": 5}}
        }]

        result = await lsp_handler.definition("test.py", 1, 5)
        assert result == {"file": "/test.py", "line": 10, "character": 5}

    @pytest.mark.asyncio
    async def test_definition_no_results(self, lsp_handler, mock_lsp_client):
        """Test definition with no results."""
        lsp_handler.register_client("python", mock_lsp_client)
        mock_lsp_client.definition.return_value = None

        result = await lsp_handler.definition("test.py", 1, 5)
        assert result is None

    @pytest.mark.asyncio
    async def test_references_success(self, lsp_handler, mock_lsp_client):
        """Test successful references request."""
        lsp_handler.register_client("python", mock_lsp_client)
        mock_lsp_client.references.return_value = [
            {
                "uri": "file:///test.py",
                "range": {"start": {"line": 10, "character": 5}}
            },
            {
                "uri": "file:///other.py",
                "range": {"start": {"line": 20, "character": 10}}
            }
        ]

        result = await lsp_handler.references("test.py", 1, 5)
        expected = [
            {"file": "/test.py", "line": 10, "character": 5},
            {"file": "/other.py", "line": 20, "character": 10}
        ]
        assert result == expected

    @pytest.mark.asyncio
    async def test_rename_success(self, lsp_handler, mock_lsp_client):
        """Test successful rename request."""
        lsp_handler.register_client("python", mock_lsp_client)
        changes = {
            "file:///test.py": [
                {"range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 5}}, "newText": "new_name"}
            ]
        }
        mock_lsp_client.rename.return_value = {"changes": changes}

        result = await lsp_handler.rename("test.py", 1, 5, "new_name")
        assert result == changes

    @pytest.mark.asyncio
    async def test_formatting_success(self, lsp_handler, mock_lsp_client):
        """Test successful formatting request."""
        lsp_handler.register_client("python", mock_lsp_client)
        mock_lsp_client.formatting.return_value = [
            {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 10, "character": 0}}, "newText": "formatted code"}
        ]

        result = await lsp_handler.formatting("test.py")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_client_for_file_python(self, lsp_handler, mock_lsp_client):
        """Test getting client for Python file."""
        lsp_handler.register_client("python", mock_lsp_client)
        result = lsp_handler._get_client_for_file("test.py")
        assert result == mock_lsp_client

    def test_get_client_for_file_unknown(self, lsp_handler):
        """Test getting client for unknown file type."""
        result = lsp_handler._get_client_for_file("test.txt")
        assert result is None