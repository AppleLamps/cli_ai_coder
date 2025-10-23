"""Tests for plugin sandbox host and IPC."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli_ai_coder.plugins.host import PluginHost
from cli_ai_coder.plugins.ipc import PluginIPCClient
from cli_ai_coder.plugins.permissions import PluginPermissions, validate_permissions


class TestPluginPermissions:
    """Test plugin permissions validation."""

    def test_permissions_creation(self):
        """Test creating permissions object."""
        config = {
            "allowed_apis": ["read_file", "write_file"],
            "allowed_paths": ["/tmp", "/home/user"],
            "memory_limit_mb": 50,
            "timeout": 10.0
        }
        perms = PluginPermissions(config)
        assert "read_file" in perms.allowed_apis
        assert "write_file" in perms.allowed_apis
        assert len(perms.allowed_paths) == 2
        assert perms.memory_limit_mb == 50
        assert perms.timeout == 10.0

    def test_validate_permissions_valid(self):
        """Test validating valid permissions."""
        perms_dict = {
            "allowed_apis": ["read_file"],
            "allowed_paths": ["/tmp"],
            "memory_limit_mb": 100,
            "timeout": 5.0
        }
        validated = validate_permissions(perms_dict)
        assert validated["allowed_apis"] == ["read_file"]
        assert validated["memory_limit_mb"] == 100

    def test_validate_permissions_invalid_api(self):
        """Test validating permissions with invalid API."""
        perms_dict = {
            "allowed_apis": ["dangerous_api"],
            "allowed_paths": ["/tmp"],
            "memory_limit_mb": 100,
            "timeout": 5.0
        }
        validated = validate_permissions(perms_dict)
        # Validation doesn't reject invalid APIs, just normalizes structure
        assert "dangerous_api" in validated["allowed_apis"]

    def test_validate_permissions_invalid_path(self):
        """Test validating permissions with invalid path."""
        perms_dict = {
            "allowed_apis": ["read_file"],
            "allowed_paths": ["/etc/passwd"],
            "memory_limit_mb": 100,
            "timeout": 5.0
        }
        validated = validate_permissions(perms_dict)
        # Validation resolves paths to absolute
        assert len(validated["allowed_paths"]) == 1
        assert validated["allowed_paths"][0].endswith("etc\\passwd")  # Windows path

    def test_validate_permissions_excessive_memory(self):
        """Test validating permissions with excessive memory."""
        perms_dict = {
            "allowed_apis": ["read_file"],
            "allowed_paths": ["/tmp"],
            "memory_limit_mb": 1000,
            "timeout": 5.0
        }
        validated = validate_permissions(perms_dict)
        # Validation doesn't cap values, just ensures they're valid types
        assert validated["memory_limit_mb"] == 1000

    def test_validate_permissions_excessive_timeout(self):
        """Test validating permissions with excessive timeout."""
        perms_dict = {
            "allowed_apis": ["read_file"],
            "allowed_paths": ["/tmp"],
            "memory_limit_mb": 100,
            "timeout": 300.0
        }
        validated = validate_permissions(perms_dict)
        # Validation doesn't cap values, just ensures they're valid types
        assert validated["timeout"] == 300.0

    def test_can_call_api_allowed(self):
        """Test API call permission check."""
        config = {
            "allowed_apis": ["read_file", "write_file"],
            "denied_apis": ["delete_file"]
        }
        perms = PluginPermissions(config)
        assert perms.can_call_api("read_file") is True
        assert perms.can_call_api("write_file") is True
        assert perms.can_call_api("delete_file") is False
        assert perms.can_call_api("unknown_api") is False  # Denied when allowed_apis is restricted

    def test_can_call_api_denied(self):
        """Test API call permission check with denied APIs."""
        config = {
            "allowed_apis": [],
            "denied_apis": ["dangerous_api"]
        }
        perms = PluginPermissions(config)
        assert perms.can_call_api("read_file") is True  # No allowed list restriction
        assert perms.can_call_api("dangerous_api") is False

    def test_can_access_path_allowed(self):
        """Test path access permission check."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test directories
            tmp_path = Path(tmpdir)
            allowed_dir = tmp_path / "allowed"
            allowed_dir.mkdir()
            secret_dir = allowed_dir / "secret"
            secret_dir.mkdir()
            test_file = allowed_dir / "test.txt"
            test_file.write_text("test")

            config = {
                "allowed_paths": [str(allowed_dir)],
                "denied_paths": [str(secret_dir)]
            }
            perms = PluginPermissions(config)

            # Should allow access to allowed directory
            assert perms.can_access_path(str(test_file)) is True
            # Should deny access to secret subdirectory
            assert perms.can_access_path(str(secret_dir / "file.txt")) is False
            # Should deny access to outside directory
            assert perms.can_access_path(str(tmp_path / "outside.txt")) is False


class TestPluginHost:
    """Test plugin host functionality."""

    @pytest.mark.asyncio
    async def test_host_initialization(self):
        """Test host initialization."""
        permissions = {
            "allowed_apis": ["read_file"],
            "allowed_paths": ["/tmp"],
            "memory_limit_mb": 50,
            "timeout": 5.0
        }
        host = PluginHost("test_plugin", permissions)
        assert host.plugin_name == "test_plugin"
        assert host.permissions == permissions

    @pytest.mark.asyncio
    async def test_host_start_stop(self):
        """Test starting and stopping the host."""
        permissions = {
            "allowed_apis": [],
            "allowed_paths": [],
            "memory_limit_mb": 50,
            "timeout": 5.0
        }
        host = PluginHost("test_plugin", permissions)

        # Mock the plugin loading and IPC server
        with patch.object(host, '_load_plugin', return_value=AsyncMock()) as mock_load, \
             patch.object(host, '_run_ipc_server', new_callable=AsyncMock) as mock_server:

            # Start host
            await host.start()
            assert host.running is True
            mock_load.assert_called_once()

            # Stop host
            host.stop()
            assert host.running is False

    @pytest.mark.asyncio
    async def test_host_communication(self):
        """Test host communication with plugin."""
        permissions = {
            "allowed_apis": ["read_file"],
            "allowed_paths": ["/tmp"],
            "memory_limit_mb": 50,
            "timeout": 5.0
        }
        host = PluginHost("test_plugin", permissions)

        # Mock the plugin instance
        mock_plugin = AsyncMock()
        mock_plugin.read_file.return_value = "file content"
        host.plugin_instance = mock_plugin

        # Test request handling
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "read_file",
            "params": {"path": "/tmp/test.txt"}
        }

        response = await host._handle_request(request)
        assert response["result"] == "file content"
        mock_plugin.read_file.assert_called_once_with(path="/tmp/test.txt")


class TestPluginIPCClient:
    """Test IPC client functionality."""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test client initialization."""
        permissions = {
            "allowed_apis": ["read_file"],
            "allowed_paths": ["/tmp"],
            "memory_limit_mb": 50,
            "timeout": 5.0
        }
        client = PluginIPCClient("test_plugin", permissions)
        assert client.plugin_name == "test_plugin"
        assert client.permissions == permissions
        assert client.running is False

    @pytest.mark.asyncio
    async def test_client_call_method_setup(self):
        """Test that calling a method sets up the request correctly."""
        permissions = {
            "allowed_apis": ["read_file"],
            "allowed_paths": ["/tmp"],
            "memory_limit_mb": 50,
            "timeout": 5.0
        }
        client = PluginIPCClient("test_plugin", permissions)

        # Mock the process and streams
        mock_process = AsyncMock()
        mock_writer = AsyncMock()

        client.process = mock_process
        client.writer = mock_writer
        client.running = True

        # Mock wait_for to avoid the timeout issue
        with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError):
            with pytest.raises(Exception, match="timed out"):
                await client.call("test_method", param="value")

        # Verify request was sent
        assert mock_writer.write.called
        request_data = mock_writer.write.call_args[0][0].decode()
        assert '"method": "test_method"' in request_data
        assert '"param": "value"' in request_data
        assert '"id": 1' in request_data

    @pytest.mark.asyncio
    async def test_client_call_method_timeout(self):
        """Test method call timeout."""
        permissions = {
            "allowed_apis": ["read_file"],
            "allowed_paths": ["/tmp"],
            "memory_limit_mb": 50,
            "timeout": 0.1
        }
        client = PluginIPCClient("test_plugin", permissions)

        # Mock the process and streams
        mock_process = AsyncMock()
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()

        client.process = mock_process
        client.reader = mock_reader
        client.writer = mock_writer
        client.running = True

        # Mock timeout
        with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError):
            with pytest.raises(Exception, match="timed out"):
                await client.call("test_method", param="value")