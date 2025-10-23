"""LSP client for diagnostics."""

import asyncio
import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.config import get_config

logger = logging.getLogger(__name__)


class LSPClient:
    """Manages a stdio LSP server process."""

    def __init__(self, language: str = "python"):
        self.language = language
        self.config = get_config()
        self.process: Optional[subprocess.Popen] = None
        self.stdin: Optional[Any] = None
        self.stdout: Optional[Any] = None
        self.stderr: Optional[Any] = None
        self.next_id = 1
        self.pending_requests: Dict[int, asyncio.Future] = {}
        self.diagnostics_callback: Optional[Callable[[str, List[Dict]], None]] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_change_time = 0
        self.change_throttle_ms = 300  # Throttle didChange notifications

    def set_diagnostics_callback(self, callback: Callable[[str, List[Dict]], None]):
        """Set callback for diagnostics updates."""
        self.diagnostics_callback = callback

    def start(self) -> bool:
        """Start the LSP server."""
        if self.running:
            return True

        cmd = self._get_command()
        if not cmd:
            logger.warning(f"No command configured for {self.language}")
            return False

        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self.stdin = self.process.stdin
            self.stdout = self.process.stdout
            self.stderr = self.process.stderr
            self.running = True

            # Start reader thread
            self.thread = threading.Thread(target=self._read_responses, daemon=True)
            self.thread.start()

            # Initialize
            self._initialize()
            return True
        except Exception as e:
            logger.error(f"Failed to start LSP server for {self.language}: {e}")
            return False

    def stop(self):
        """Stop the LSP server."""
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def restart(self) -> bool:
        """Restart the LSP server."""
        self.stop()
        time.sleep(0.5)  # Brief pause
        return self.start()

    def _get_command(self) -> Optional[List[str]]:
        """Get the command to start the LSP server."""
        if self.language == "python":
            cmd = self.config.lsp_python_cmd
            return [cmd] if cmd else None
        return None

    def _initialize(self):
        """Send initialize request."""
        params = {
            "processId": None,
            "rootPath": str(Path.cwd()),
            "rootUri": f"file://{Path.cwd()}",
            "capabilities": {
                "textDocument": {
                    "publishDiagnostics": True,
                    "hover": {"dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                    "semanticTokens": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True}
                }
            }
        }
        self._send_request("initialize", params)

        # Send initialized notification
        self._send_notification("initialized", {})

    def did_open(self, file_path: str, content: str):
        """Notify server that a file was opened."""
        if not self.running:
            return
        uri = f"file://{file_path}"
        params = {
            "textDocument": {
                "uri": uri,
                "languageId": self._get_language_id(file_path),
                "version": 1,
                "text": content
            }
        }
        self._send_notification("textDocument/didOpen", params)

    def did_change(self, file_path: str, content: str, version: int = 1):
        """Notify server that a file changed."""
        if not self.running:
            return

        # Throttle didChange notifications
        current_time = time.time() * 1000  # milliseconds
        if current_time - self.last_change_time < self.change_throttle_ms:
            return
        self.last_change_time = current_time

        uri = f"file://{file_path}"
        params = {
            "textDocument": {
                "uri": uri,
                "version": version
            },
            "contentChanges": [
                {
                    "text": content
                }
            ]
        }
        self._send_notification("textDocument/didChange", params)

    async def hover(self, file_path: str, line: int, character: int) -> Optional[Dict]:
        """Request hover information."""
        if not self.running:
            return None

        uri = f"file://{file_path}"
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character}
        }
        return await self._send_request_async("textDocument/hover", params)

    async def definition(self, file_path: str, line: int, character: int) -> Optional[List[Dict]]:
        """Request go-to-definition."""
        if not self.running:
            return None

        uri = f"file://{file_path}"
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character}
        }
        result = await self._send_request_async("textDocument/definition", params)
        if result and isinstance(result, list):
            return result
        elif result and isinstance(result, dict):
            return [result]
        return None

    async def references(self, file_path: str, line: int, character: int, include_declaration: bool = True) -> Optional[List[Dict]]:
        """Request find references."""
        if not self.running:
            return None

        uri = f"file://{file_path}"
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": include_declaration}
        }
        result = await self._send_request_async("textDocument/references", params)
        return result if isinstance(result, list) else None

    async def rename(self, file_path: str, line: int, character: int, new_name: str) -> Optional[Dict]:
        """Request rename."""
        if not self.running:
            return None

        uri = f"file://{file_path}"
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "newName": new_name
        }
        return await self._send_request_async("textDocument/rename", params)

    async def semantic_tokens_full(self, file_path: str) -> Optional[Dict]:
        """Request semantic tokens for the full document."""
        if not self.running:
            return None

        uri = f"file://{file_path}"
        params = {
            "textDocument": {"uri": uri}
        }
        return await self._send_request_async("textDocument/semanticTokens/full", params)

    async def semantic_tokens_range(self, file_path: str, start_line: int, start_char: int, end_line: int, end_char: int) -> Optional[Dict]:
        """Request semantic tokens for a range."""
        if not self.running:
            return None

        uri = f"file://{file_path}"
        params = {
            "textDocument": {"uri": uri},
            "range": {
                "start": {"line": start_line, "character": start_char},
                "end": {"line": end_line, "character": end_char}
            }
        }
        return await self._send_request_async("textDocument/semanticTokens/range", params)

    async def code_action(self, file_path: str, range_start_line: int, range_start_char: int, 
                         range_end_line: int, range_end_char: int, 
                         diagnostics: Optional[List[Dict]] = None) -> Optional[List[Dict]]:
        """Request code actions for a range."""
        if not self.running:
            return None

        uri = f"file://{file_path}"
        params = {
            "textDocument": {"uri": uri},
            "range": {
                "start": {"line": range_start_line, "character": range_start_char},
                "end": {"line": range_end_line, "character": range_end_char}
            },
            "context": {
                "diagnostics": diagnostics or []
            }
        }
        result = await self._send_request_async("textDocument/codeAction", params)
        return result if isinstance(result, list) else None

    async def execute_command(self, command: str, arguments: Optional[List[Any]] = None) -> Optional[Any]:
        """Execute a workspace command."""
        if not self.running:
            return None

        params = {
            "command": command,
            "arguments": arguments or []
        }
        return await self._send_request_async("workspace/executeCommand", params)

    async def _send_request_async(self, method: str, params: Dict) -> Optional[Any]:
        """Send an async request and return the result."""
        if not self.running or not self.stdin:
            return None

        request_id = self.next_id
        self.next_id += 1

        future = asyncio.Future()
        self.pending_requests[request_id] = future

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }

        message = f"Content-Length: {len(json.dumps(request))}\r\n\r\n{json.dumps(request)}"
        try:
            self.stdin.write(message)
            self.stdin.flush()
        except Exception as e:
            logger.error(f"Failed to send request: {e}")
            self.pending_requests.pop(request_id, None)
            return None

        try:
            # Wait for response with timeout
            result = await asyncio.wait_for(future, timeout=5.0)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Request {method} timed out")
            self.pending_requests.pop(request_id, None)
            return None
        except Exception as e:
            logger.error(f"Error in async request: {e}")
            return None

    def _get_language_id(self, file_path: str) -> str:
        """Get language ID for file."""
        if file_path.endswith('.py'):
            return 'python'
        return 'plaintext'

    def _send_request(self, method: str, params: Dict) -> int:
        """Send a request and return the ID."""
        if not self.running or not self.stdin:
            return -1

        request_id = self.next_id
        self.next_id += 1

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }

        message = f"Content-Length: {len(json.dumps(request))}\r\n\r\n{json.dumps(request)}"
        try:
            self.stdin.write(message)
            self.stdin.flush()
        except Exception as e:
            logger.error(f"Failed to send request: {e}")

        return request_id

    def _send_notification(self, method: str, params: Dict):
        """Send a notification."""
        if not self.running or not self.stdin:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }

        message = f"Content-Length: {len(json.dumps(notification))}\r\n\r\n{json.dumps(notification)}"
        try:
            self.stdin.write(message)
            self.stdin.flush()
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def _read_responses(self):
        """Read responses from the server in a separate thread."""
        if not self.stdout:
            return

        buffer = ""
        while self.running:
            try:
                char = self.stdout.read(1)
                if not char:
                    break
                buffer += char

                # Check for complete message
                if "\r\n\r\n" in buffer:
                    header_end = buffer.find("\r\n\r\n")
                    header = buffer[:header_end]
                    body_start = header_end + 4

                    # Parse Content-Length
                    content_length = 0
                    for line in header.split("\r\n"):
                        if line.startswith("Content-Length:"):
                            content_length = int(line.split(":", 1)[1].strip())
                            break

                    if content_length > 0 and len(buffer) >= body_start + content_length:
                        body = buffer[body_start:body_start + content_length]
                        buffer = buffer[body_start + content_length:]

                        try:
                            response = json.loads(body)
                            self._handle_response(response)
                        except json.JSONDecodeError:
                            logger.error(f"Invalid JSON response: {body}")
            except Exception as e:
                logger.error(f"Error reading from LSP server: {e}")
                break

    def _handle_response(self, response: Dict):
        """Handle a response from the server."""
        if "method" in response:
            # Notification
            self._handle_notification(response["method"], response.get("params", {}))
        elif "id" in response:
            # Response to request
            request_id = response["id"]
            if request_id in self.pending_requests:
                future = self.pending_requests.pop(request_id)
                if "error" in response:
                    future.set_exception(Exception(response["error"]))
                else:
                    future.set_result(response.get("result"))

    def _handle_notification(self, method: str, params: Dict):
        """Handle a notification from the server."""
        if method == "textDocument/publishDiagnostics":
            self._handle_publish_diagnostics(params)

    def _handle_publish_diagnostics(self, params: Dict):
        """Handle publishDiagnostics notification."""
        uri = params.get("uri", "")
        if uri.startswith("file://"):
            file_path = uri[7:]  # Remove file:// prefix
            diagnostics = params.get("diagnostics", [])
            if self.diagnostics_callback:
                self.diagnostics_callback(file_path, diagnostics)