"""Sandboxed plugin host process."""

import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PluginHost:
    """Sandboxed plugin host that runs in a separate process."""

    def __init__(self, plugin_name: str, permissions: Dict[str, Any]):
        self.plugin_name = plugin_name
        self.permissions = permissions
        self.running = False
        self.plugin_instance = None

    async def start(self):
        """Start the plugin host."""
        logger.info(f"Starting plugin host for {self.plugin_name}")
        self.running = True

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Load and initialize plugin
        try:
            self.plugin_instance = await self._load_plugin()
            logger.info(f"Plugin {self.plugin_name} loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load plugin {self.plugin_name}: {e}")
            return

        # Start IPC server
        await self._run_ipc_server()

    async def _load_plugin(self):
        """Load the plugin module safely."""
        # Import the plugin module
        plugin_module_name = f"plugins.{self.plugin_name}"
        try:
            __import__(plugin_module_name)
            plugin_module = sys.modules[plugin_module_name]
        except ImportError as e:
            raise Exception(f"Could not import plugin {plugin_module_name}: {e}")

        # Find the plugin class (assuming it follows naming convention)
        plugin_class_name = f"{self.plugin_name.capitalize()}Provider"
        if not hasattr(plugin_module, plugin_class_name):
            raise Exception(f"Plugin class {plugin_class_name} not found in {plugin_module_name}")

        plugin_class = getattr(plugin_module, plugin_class_name)

        # Instantiate the plugin
        return plugin_class()

    async def _run_ipc_server(self):
        """Run the IPC server for communication with main process."""
        logger.info("Starting IPC server")

        # Read from stdin, write to stdout
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

        writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

        while self.running:
            try:
                # Read JSON-RPC request
                line = await reader.readline()
                if not line:
                    break

                request_str = line.decode().strip()
                if not request_str:
                    continue

                logger.debug(f"Received request: {request_str}")

                # Parse request
                try:
                    request = json.loads(request_str)
                except json.JSONDecodeError as e:
                    await self._send_error(writer, None, -32700, f"Parse error: {e}")
                    continue

                # Handle request
                response = await self._handle_request(request)
                await self._send_response(writer, response)

            except Exception as e:
                logger.error(f"Error handling request: {e}")
                break

        logger.info("IPC server stopped")

    async def _handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a JSON-RPC request."""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if not method:
            return self._error_response(request_id, -32600, "Invalid Request: missing method")

        # Check permissions
        if not self._check_permission(method, params):
            return self._error_response(request_id, -32603, f"Permission denied for method {method}")

        # Route to plugin method
        try:
            if not hasattr(self.plugin_instance, method):
                return self._error_response(request_id, -32601, f"Method not found: {method}")

            method_func = getattr(self.plugin_instance, method)

            # Call the method (assuming it's async)
            if asyncio.iscoroutinefunction(method_func):
                result = await method_func(**params)
            else:
                result = method_func(**params)

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }

        except Exception as e:
            logger.error(f"Error calling method {method}: {e}")
            return self._error_response(request_id, -32603, f"Internal error: {e}")

    def _check_permission(self, method: str, params: Dict[str, Any]) -> bool:
        """Check if the requested method is allowed."""
        # Get allowed APIs from permissions
        allowed_apis = self.permissions.get("allowed_apis", [])

        # Check if method is in allowed APIs
        if method not in allowed_apis:
            logger.warning(f"Method {method} not in allowed APIs: {allowed_apis}")
            return False

        # Check path restrictions
        if "path" in params:
            path = Path(params["path"])
            allowed_paths = self.permissions.get("allowed_paths", [])
            if not any(path.is_relative_to(allowed_path) for allowed_path in allowed_paths):
                logger.warning(f"Path {path} not in allowed paths: {allowed_paths}")
                return False

        return True

    def _error_response(self, request_id, code: int, message: str) -> Dict[str, Any]:
        """Create an error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }

    async def _send_response(self, writer, response: Dict[str, Any]):
        """Send a JSON-RPC response."""
        response_str = json.dumps(response) + "\n"
        writer.write(response_str.encode())
        await writer.drain()

    async def _send_error(self, writer, request_id, code: int, message: str):
        """Send an error response."""
        error_response = self._error_response(request_id, code, message)
        await self._send_response(writer, error_response)

    def _signal_handler(self, signum, frame):
        """Handle termination signals."""
        logger.info(f"Received signal {signum}, shutting down")
        self.running = False

    def stop(self):
        """Stop the plugin host."""
        self.running = False


async def main():
    """Main entry point for the plugin host process."""
    if len(sys.argv) < 3:
        print("Usage: python -m plugins.host <plugin_name> <permissions_json>", file=sys.stderr)
        sys.exit(1)

    plugin_name = sys.argv[1]
    permissions_json = sys.argv[2]

    try:
        permissions = json.loads(permissions_json)
    except json.JSONDecodeError as e:
        print(f"Invalid permissions JSON: {e}", file=sys.stderr)
        sys.exit(1)

    host = PluginHost(plugin_name, permissions)

    try:
        await host.start()
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down")
    except Exception as e:
        logger.error(f"Host failed: {e}")
    finally:
        host.stop()


if __name__ == "__main__":
    asyncio.run(main())