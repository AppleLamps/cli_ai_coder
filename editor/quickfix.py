"""LSP Quick Fix implementation."""

import asyncio
from typing import Any, Dict, List, Optional

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Button, Dialog, Label, RadioList

from editor.diffview import show_diff_viewer
from language.lsp_client import LSPClient


class QuickFixManager:
    """Manages LSP quick fix functionality."""

    def __init__(self, lsp_client: LSPClient, app: Application):
        self.lsp_client = lsp_client
        self.app = app

    async def show_quick_fix(self, file_path: str, line: int, character: int) -> None:
        """Show quick fix modal for the given position."""
        # Get diagnostics for context
        diagnostics = []  # TODO: Get diagnostics from diagnostics manager

        # Query code actions
        actions = await self.lsp_client.code_action(
            file_path, line, character, line, character, diagnostics
        )

        if not actions:
            # No actions available
            return

        # Filter for quickfix kind
        quickfix_actions = [
            action for action in actions
            if action.get("kind") == "quickfix" or
               "fix" in action.get("title", "").lower() or
               "import" in action.get("title", "").lower()
        ]

        if not quickfix_actions:
            return

        # Show modal with actions
        await self._show_action_modal(file_path, quickfix_actions)

    async def _show_action_modal(self, file_path: str, actions: List[Dict]) -> None:
        """Show modal to select a code action."""
        action_list = RadioList([
            (action, action.get("title", "Unknown action"))
            for action in actions
        ])

        def accept():
            selected_action = action_list.current_value
            if selected_action:
                asyncio.create_task(self._apply_action(file_path, selected_action))
            self.app.exit()

        def cancel():
            self.app.exit()

        dialog = Dialog(
            title="Quick Fix",
            body=action_list,
            buttons=[
                Button(text="Apply", handler=accept),
                Button(text="Cancel", handler=cancel),
            ],
            modal=True,
        )

        # Create temporary app for modal
        temp_app = Application(
            layout=Layout(dialog),
            key_bindings=self._get_modal_keybindings(accept, cancel),
            style=self.app.style,
            full_screen=False,
        )

        await temp_app.run_async()

    def _get_modal_keybindings(self, accept, cancel):
        """Get key bindings for the modal."""
        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            accept()

        @kb.add("escape")
        def _(event):
            cancel()

        return kb

    async def _apply_action(self, file_path: str, action: Dict) -> None:
        """Apply the selected code action."""
        if "edit" in action:
            # Has edits - show diff viewer
            workspace_edit = action["edit"]
            await self._apply_workspace_edit(workspace_edit)
        elif "command" in action:
            # Has command - execute it
            command = action["command"]
            arguments = action.get("arguments", [])
            result = await self.lsp_client.execute_command(command, arguments)
            # Refresh diagnostics after command
            # TODO: Trigger diagnostics refresh
        else:
            # Unknown action type
            pass

    async def _apply_workspace_edit(self, workspace_edit: Dict) -> None:
        """Apply a workspace edit by showing diff viewer."""
        # Convert workspace edit to unified diff
        # This is simplified - real implementation would parse the edit properly
        diff_text = self._workspace_edit_to_diff(workspace_edit)
        if diff_text:
            show_diff_viewer(diff_text, self.app)

    def _workspace_edit_to_diff(self, workspace_edit: Dict) -> str:
        """Convert workspace edit to unified diff format."""
        # Simplified implementation
        # Real implementation would parse changes and create proper diff
        changes = workspace_edit.get("changes", {})
        diff_lines = []

        for uri, edits in changes.items():
            file_path = uri.replace("file://", "")
            diff_lines.append(f"--- a/{file_path}")
            diff_lines.append(f"+++ b/{file_path}")

            for edit in edits:
                # Simplified - just show the new text
                new_text = edit.get("newText", "")
                if new_text:
                    diff_lines.extend(new_text.splitlines())

        return "\n".join(diff_lines) if diff_lines else ""