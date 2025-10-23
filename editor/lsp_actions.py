"""LSP actions for hover, definitions, references, rename, and formatting."""

import asyncio
from typing import Any, Callable, Dict, List, Optional

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Button, TextArea

from editor.buffers import BufferManager
from editor.semantics import SemanticTokensManager
from editor.statusbar import StatusBar
from language.lsp_client import LSPClient


class LSPActionHandler:
    """Handles LSP actions like hover, definitions, etc."""

    def __init__(self, buffer_manager: Optional[BufferManager], status_bar: Optional[StatusBar]):
        self.buffer_manager = buffer_manager
        self.status_bar = status_bar
        self.lsp_clients: Dict[str, LSPClient] = {}
        self.semantic_tokens_manager = SemanticTokensManager()

    def get_client(self, language: str) -> Optional[LSPClient]:
        """Get LSP client for language."""
        return self.lsp_clients.get(language)

    def register_client(self, language: str, client: LSPClient):
        """Register LSP client."""
        self.lsp_clients[language] = client

    async def hover(self, file_path: str, line: int, character: int) -> Optional[str]:
        """Get hover information."""
        client = self._get_client_for_file(file_path)
        if not client:
            return None

        try:
            result = await client.hover(file_path, line, character)
            if result and "contents" in result:
                contents = result["contents"]
                if isinstance(contents, str):
                    return contents
                elif isinstance(contents, dict) and "value" in contents:
                    return contents["value"]
                elif isinstance(contents, list):
                    return "\n".join(str(c.get("value", c)) if isinstance(c, dict) else str(c) for c in contents)
        except Exception as e:
            if self.status_bar:
                self.status_bar.set_message(f"Hover error: {e}")
        return None

    async def definition(self, file_path: str, line: int, character: int) -> Optional[Dict]:
        """Go to definition."""
        client = self._get_client_for_file(file_path)
        if not client:
            return None

        try:
            result = await client.definition(file_path, line, character)
            if result and len(result) > 0:
                location = result[0]
                if "uri" in location and "range" in location:
                    uri = location["uri"]
                    if uri.startswith("file://"):
                        target_file = uri[7:]
                        start = location["range"]["start"]
                        return {
                            "file": target_file,
                            "line": start["line"],
                            "character": start["character"]
                        }
        except Exception as e:
            if self.status_bar:
                self.status_bar.set_message(f"Definition error: {e}")
        return None

    async def references(self, file_path: str, line: int, character: int) -> Optional[List[Dict]]:
        """Find references."""
        client = self._get_client_for_file(file_path)
        if not client:
            return None

        try:
            result = await client.references(file_path, line, character)
            if result:
                refs = []
                for ref in result:
                    if "uri" in ref and "range" in ref:
                        uri = ref["uri"]
                        if uri.startswith("file://"):
                            ref_file = uri[7:]
                            start = ref["range"]["start"]
                            refs.append({
                                "file": ref_file,
                                "line": start["line"],
                                "character": start["character"]
                            })
                return refs
        except Exception as e:
            if self.status_bar:
                self.status_bar.set_message(f"References error: {e}")
        return None

    async def rename(self, file_path: str, line: int, character: int, new_name: str) -> Optional[Dict]:
        """Rename symbol."""
        client = self._get_client_for_file(file_path)
        if not client:
            return None

        try:
            result = await client.rename(file_path, line, character, new_name)
            if result and "changes" in result:
                return result["changes"]
        except Exception as e:
            if self.status_bar:
                self.status_bar.set_message(f"Rename error: {e}")
        return None

    async def formatting(self, file_path: str) -> Optional[List[Dict]]:
        """Format document."""
        client = self._get_client_for_file(file_path)
        if not client:
            return None

        try:
            result = await client.formatting(file_path)
            return result
        except Exception as e:
            if self.status_bar:
                self.status_bar.set_message(f"Formatting error: {e}")
        return None

    async def semantic_tokens_full(self, file_path: str) -> Optional[List[Dict]]:
        """Get semantic tokens for file."""
        client = self._get_client_for_file(file_path)
        if not client:
            return None

        try:
            result = await client.semantic_tokens_full(file_path)
            if result and "data" in result:
                # Decode the token data
                tokens = self._decode_semantic_tokens(result["data"])
                self.semantic_tokens_manager.update_tokens(file_path, tokens)
                return tokens
        except Exception as e:
            if self.status_bar:
                self.status_bar.set_message(f"Semantic tokens error: {e}")
        return None

    async def organize_imports(self, file_path: str) -> Optional[List[Dict]]:
        """Organize imports in file."""
        client = self._get_client_for_file(file_path)
        if not client:
            return None

        try:
            # Get code actions for the entire document
            actions = await client.code_action(file_path, 0, 0, 1000000, 0)  # Large range for whole file
            if actions:
                # Find organize imports action
                for action in actions:
                    title = action.get("title", "").lower()
                    if "organize imports" in title or "organizeimports" in title:
                        # Execute the command if present
                        if "command" in action:
                            command = action["command"]
                            arguments = action.get("arguments", [])
                            result = await client.execute_command(command, arguments)
                            return result
                        # Or apply edits directly
                        elif "edit" in action:
                            return action["edit"].get("changes", {}).get(f"file://{file_path}", [])
        except Exception as e:
            if self.status_bar:
                self.status_bar.set_message(f"Organize imports error: {e}")
        return None

    async def code_action(self, file_path: str, line: int, character: int, diagnostics: Optional[List[Dict]] = None) -> Optional[List[Dict]]:
        """Get code actions for position."""
        client = self._get_client_for_file(file_path)
        if not client:
            return None

        try:
            # Get a small range around the cursor for code actions
            actions = await client.code_action(file_path, line, character, line, character + 1, diagnostics)
            return actions
        except Exception as e:
            if self.status_bar:
                self.status_bar.set_message(f"Code action error: {e}")
        return None

    async def execute_command(self, command: str, arguments: Optional[List] = None) -> Optional[Any]:
        """Execute a workspace command."""
        # Find any client to execute command (commands are workspace-wide)
        client = next(iter(self.lsp_clients.values()), None)
        if not client:
            return None

        try:
            result = await client.execute_command(command, arguments)
            return result
        except Exception as e:
            if self.status_bar:
                self.status_bar.set_message(f"Execute command error: {e}")
        return None

    def _decode_semantic_tokens(self, data: List[int]) -> List[Dict]:
        """Decode LSP semantic token data."""
        tokens = []
        line = 0
        char = 0

        for i in range(0, len(data), 5):
            if i + 4 >= len(data):
                break

            delta_line = data[i]
            delta_start = data[i + 1]
            length = data[i + 2]
            token_type = data[i + 3]
            token_modifiers = data[i + 4]

            line += delta_line
            if delta_line == 0:
                char += delta_start
            else:
                char = delta_start

            # Decode modifiers (bit flags)
            modifiers = []
            for j, mod in enumerate(LSPActionHandler.TOKEN_MODIFIERS):
                if token_modifiers & (1 << j):
                    modifiers.append(mod)

            tokens.append({
                "line": line,
                "start": char,
                "length": length,
                "type": LSPActionHandler.TOKEN_TYPES[token_type] if token_type < len(LSPActionHandler.TOKEN_TYPES) else "unknown",
                "modifiers": modifiers
            })

        return tokens

    # LSP semantic token types and modifiers constants
    TOKEN_TYPES = [
        "namespace", "type", "class", "enum", "interface", "struct", "typeParameter",
        "parameter", "variable", "property", "enumMember", "event", "function",
        "method", "macro", "keyword", "modifier", "comment", "string", "number",
        "regexp", "operator"
    ]

    TOKEN_MODIFIERS = [
        "declaration", "definition", "readonly", "static", "deprecated", "abstract",
        "async", "modification", "documentation", "defaultLibrary"
    ]

    def _get_client_for_file(self, file_path: str) -> Optional[LSPClient]:
        """Get appropriate LSP client for file."""
        if file_path.endswith('.py'):
            return self.lsp_clients.get('python')
        return None


class HoverPopup:
    """Simple hover popup."""

    def __init__(self, content: str):
        self.content = content
        self.visible = True

    def get_layout(self):
        """Get popup layout."""
        from prompt_toolkit.layout import ConditionalContainer

        return ConditionalContainer(
            Window(
                FormattedTextControl(text=self.content),
                width=60,
                height=10
            ),
            filter=self.visible
        )

    def hide(self):
        """Hide popup."""
        self.visible = False


class ReferencesDialog:
    """Dialog to show references."""

    def __init__(self, references: List[Dict], on_select: Callable[[Dict], None]):
        self.references = references
        self.on_select = on_select
        self.selected_index = 0
        self.visible = True

        self.control = FormattedTextControl(text=self._format_refs())

    def get_layout(self):
        """Get dialog layout."""
        from prompt_toolkit.layout import ConditionalContainer

        return ConditionalContainer(
            Window(self.control, width=80, height=15),
            filter=self.visible
        )

    def select(self):
        """Select current reference."""
        if 0 <= self.selected_index < len(self.references):
            self.on_select(self.references[self.selected_index])
            self.visible = False

    def next_ref(self):
        """Move to next reference."""
        if self.references:
            self.selected_index = (self.selected_index + 1) % len(self.references)
            self.control.text = self._format_refs()

    def prev_ref(self):
        """Move to previous reference."""
        if self.references:
            self.selected_index = (self.selected_index - 1) % len(self.references)
            self.control.text = self._format_refs()

    def _format_refs(self) -> str:
        """Format references for display."""
        lines = ["References (Enter to jump, j/k to navigate):", ""]
        for i, ref in enumerate(self.references):
            marker = ">" if i == self.selected_index else " "
            lines.append(f"{marker} {ref['file']}:{ref['line'] + 1}:{ref['character']}")
        return "\n".join(lines)


class RenameDialog:
    """Dialog for rename input."""

    def __init__(self, current_name: str, on_rename: Callable[[str], None]):
        self.current_name = current_name
        self.on_rename = on_rename
        self.visible = True
        self.input_buffer = None

    def get_layout(self):
        """Get dialog layout."""
        from prompt_toolkit.layout import ConditionalContainer
        from prompt_toolkit.buffer import Buffer
        from prompt_toolkit.layout.controls import BufferControl

        if self.input_buffer is None:
            self.input_buffer = Buffer()
            self.input_buffer.text = self.current_name

        return ConditionalContainer(
            HSplit([
                Window(content=FormattedTextControl(text=f"Rename '{self.current_name}' to:"), height=1),
                Window(content=BufferControl(self.input_buffer), height=3),
                Button("Rename", handler=self.do_rename),
                Button("Cancel", handler=self.cancel)
            ]),
            filter=self.visible
        )

    def do_rename(self):
        """Perform rename."""
        if self.input_buffer:
            new_name = self.input_buffer.text.strip()
            if new_name and new_name != self.current_name:
                self.on_rename(new_name)
        self.visible = False

    def cancel(self):
        """Cancel rename."""
        self.visible = False


# Global handler instance
lsp_handler = LSPActionHandler(None, None)  # Will be initialized in app.py