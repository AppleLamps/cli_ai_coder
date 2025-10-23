"""JSON-RPC over stdio IPC for plugin communication."""

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Awaitable
import logging

logger = logging.getLogger(__name__)


class PluginIPCClient:
    """Client for communicating with a plugin host process."""

    def __init__(self, plugin_name: str, permissions: Dict[str, Any]):
        self.plugin_name = plugin_name
        self.permissions = permissions
        self.process: Optional[subprocess.Popen] = None
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.request_id = 0
        self.pending_requests: Dict[int, asyncio.Future] = {}
        self.running = False

    async def start(self) -> bool:
        """Start the plugin host process."""
        try:
            # Prepare environment (restricted)
            env = os.environ.copy()
            # Remove potentially dangerous environment variables
            dangerous_vars = ['LD_PRELOAD', 'DYLD_LIBRARY_PATH', 'PATH']
            for var in dangerous_vars:
                if var in env:
                    # Keep PATH but restrict it
                    if var == 'PATH':
                        env[var] = '/usr/local/bin:/usr/bin:/bin'  # Minimal PATH
                    else:
                        del env[var]

            # Set working directory to project root
            cwd = Path.cwd()

            # Prepare permissions as JSON
            permissions_json = json.dumps(self.permissions)

            # Start the host process
            self.process = subprocess.Popen(
                [sys.executable, "-m", "plugins.host", self.plugin_name, permissions_json],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=cwd
            )

            # Set up async readers
            loop = asyncio.get_event_loop()
            self.reader = asyncio.StreamReader()
            reader_protocol = asyncio.StreamReaderProtocol(self.reader)
            await loop.connect_read_pipe(lambda: reader_protocol, self.process.stdout)

            writer_transport, writer_protocol = await loop.connect_write_pipe(
                asyncio.streams.FlowControlMixin, self.process.stdin
            )
            self.writer = asyncio.StreamWriter(writer_transport, writer_protocol, self.reader, loop)

            self.running = True

            # Start response reader task
            asyncio.create_task(self._read_responses())

            # Wait a bit for the process to start
            await asyncio.sleep(0.1)

            # Check if process is still alive
            if self.process.poll() is not None:
                if self.process.stderr:
                    stderr = self.process.stderr.read().decode()
                    logger.error(f"Plugin host failed to start: {stderr}")
                return False

            logger.info(f"Plugin host for {self.plugin_name} started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start plugin host: {e}")
            return False

    async def stop(self):
        """Stop the plugin host process."""
        self.running = False

        if self.process:
            try:
                # Try graceful shutdown first
                if hasattr(self.process, 'terminate'):
                    self.process.terminate()

                # Wait a bit
                await asyncio.sleep(0.5)

                # Force kill if still running
                if self.process.poll() is None:
                    self.process.kill()

                # Wait for process to exit
                try:
                    await asyncio.wait_for(asyncio.create_subprocess_shell(""), timeout=2.0)
                except asyncio.TimeoutError:
                    pass

            except Exception as e:
                logger.error(f"Error stopping plugin host: {e}")

        # Cancel pending requests
        for future in self.pending_requests.values():
            if not future.done():
                future.cancel()

        self.pending_requests.clear()

    async def call(self, method: str, **params) -> Any:
        """Make a JSON-RPC call to the plugin."""
        if not self.running or not self.writer:
            raise Exception("Plugin host not running")

        self.request_id += 1
        request_id = self.request_id

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }

        # Create future for response
        future = asyncio.Future()
        self.pending_requests[request_id] = future

        # Send request
        request_str = json.dumps(request) + "\n"
        self.writer.write(request_str.encode())
        await self.writer.drain()

        # Wait for response with timeout
        try:
            response = await asyncio.wait_for(future, timeout=self.permissions.get("timeout", 5.0))
            return response
        except asyncio.TimeoutError:
            # Remove from pending
            del self.pending_requests[request_id]
            raise Exception(f"Call to {method} timed out")
        finally:
            # Clean up
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]

    async def _read_responses(self):
        """Read responses from the plugin host."""
        if not self.reader:
            return

        while self.running:
            try:
                line = await self.reader.readline()
                if not line:
                    break

                response_str = line.decode().strip()
                if not response_str:
                    continue

                try:
                    response = json.loads(response_str)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON response: {response_str}")
                    continue

                # Handle response
                await self._handle_response(response)

            except Exception as e:
                logger.error(f"Error reading response: {e}")
                break

    async def _handle_response(self, response: Dict[str, Any]):
        """Handle a JSON-RPC response."""
        response_id = response.get("id")

        if response_id in self.pending_requests:
            future = self.pending_requests[response_id]

            if "result" in response:
                future.set_result(response["result"])
            elif "error" in response:
                error = response["error"]
                exception = Exception(f"RPC Error {error.get('code', 0)}: {error.get('message', 'Unknown error')}")
                future.set_exception(exception)
            else:
                future.set_exception(Exception("Invalid response format"))


class PluginIPCManager:
    """Manager for plugin IPC connections."""

    def __init__(self):
        self.clients: Dict[str, PluginIPCClient] = {}
        self.timeouts: Dict[str, float] = {}

    async def start_plugin(self, plugin_name: str, permissions: Dict[str, Any]) -> bool:
        """Start a plugin host."""
        if plugin_name in self.clients:
            await self.stop_plugin(plugin_name)

        client = PluginIPCClient(plugin_name, permissions)
        success = await client.start()

        if success:
            self.clients[plugin_name] = client
            self.timeouts[plugin_name] = time.time()
        else:
            logger.error(f"Failed to start plugin {plugin_name}")

        return success

    async def stop_plugin(self, plugin_name: str):
        """Stop a plugin host."""
        if plugin_name in self.clients:
            await self.clients[plugin_name].stop()
            del self.clients[plugin_name]

        if plugin_name in self.timeouts:
            del self.timeouts[plugin_name]

    async def call_plugin(self, plugin_name: str, method: str, **params) -> Any:
        """Call a method on a plugin."""
        if plugin_name not in self.clients:
            raise Exception(f"Plugin {plugin_name} not running")

        client = self.clients[plugin_name]

        # Update last activity
        self.timeouts[plugin_name] = time.time()

        return await client.call(method, **params)

    async def stop_all(self):
        """Stop all plugin hosts."""
        plugin_names = list(self.clients.keys())
        for plugin_name in plugin_names:
            await self.stop_plugin(plugin_name)

    def is_plugin_running(self, plugin_name: str) -> bool:
        """Check if a plugin is running."""
        return plugin_name in self.clients and self.clients[plugin_name].running

    async def cleanup_idle_plugins(self, idle_timeout: float = 300.0):
        """Stop plugins that have been idle for too long."""
        current_time = time.time()
        to_stop = []

        for plugin_name, last_activity in self.timeouts.items():
            if current_time - last_activity > idle_timeout:
                to_stop.append(plugin_name)

        for plugin_name in to_stop:
            logger.info(f"Stopping idle plugin {plugin_name}")
            await self.stop_plugin(plugin_name)


# Global IPC manager instance
ipc_manager = PluginIPCManager()