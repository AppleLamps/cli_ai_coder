"""Basic TUI editor application."""

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import ConditionalContainer, Dimension, HSplit, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Button, Dialog, Label, RadioList, TextArea

from ai.patches import apply_unified_diff, is_unified_diff, parse_affected_paths, split_hunks, apply_selected_hunks
from ai.router import TaskType
from ai.tools import run_tests
from editor.buffers import BufferManager
from editor.diffview import show_diff_viewer
from editor.commands import registry
from editor.filetree import flatten_tree_for_display, get_directory_tree
from editor.search import fuzzy_search_files, get_project_files
from editor.statusbar import StatusBar
from editor.gutter import GitStatusGutter
from editor.diagnostics import LSPDiagnosticsManager
from editor.quickfix import QuickFixManager
from core.config import get_config
from core.telemetry import telemetry
from editor.telemetry_wizard import run_telemetry_wizard


class AIPanel:
    """AI interaction panel."""

    def __init__(self, buffer_manager: BufferManager, status_bar: StatusBar):
        self.buffer_manager = buffer_manager
        self.status_bar = status_bar
        self.status_label = Label(text="Ready")

    def get_layout(self):
        """Get the panel layout."""
        return ConditionalContainer(
            HSplit([
                Window(content=Label(text="AI Panel"), height=1),
                Window(content=self.task_selector, height=4),
                Window(content=self.instruction_input, height=4),
                Window(content=self.output_area, height=10),
                Window(content=self.status_label, height=1),
            ]),
            filter=self.visible
        )

    def toggle(self):
        """Toggle panel visibility."""
        self.visible = not self.visible

    def run_task(self):
        """Run the selected AI task."""
        active_buffer = self.buffer_manager.active()
        if not active_buffer or not active_buffer.path:
            self.status_bar.set_message("No active file")
            return

        code = active_buffer.text
        filename = str(active_buffer.path)
        instruction = self.instruction_input.text

        # Map radio selection to TaskType
        task_map = {
            "explain": TaskType.EXPLAIN,
            "refactor": TaskType.REFACTOR,
            "fix_error": TaskType.FIX_ERROR,
            "add_tests": TaskType.ADD_TESTS,
            "fix_tests": TaskType.FIX_TESTS
        }
        task_type = task_map.get(self.task_selector.current_value, TaskType.EXPLAIN)

        # Track task execution
        telemetry.track_feature_usage("ai_task", {"task_type": task_type.value, "has_instruction": bool(instruction)})

        self.output_text = ""
        self.diff_text = ""
        self.has_diff = False
        self.streaming = True
        self.status_bar.set_message(f"Running {task_type.value}...")

        def stream_callback(chunk: str):
            self.output_text += chunk
            self.output_area.text = self.output_text

        def completion_callback():
            self.streaming = False
            self.status_bar.set_message("Complete")
            # Check if output is a diff
            if is_unified_diff(self.output_text):
                self.diff_text = self.output_text
                self.has_diff = True
                # Show diff viewer
                self.show_diff_viewer()
            else:
                self.has_diff = False

        # Run in background
        asyncio.create_task(self._run_task_async(
            task_type, code, filename, instruction, stream_callback, completion_callback
        ))

    async def _run_task_async(self, task_type, code, filename, instruction, callback, completion):
        """Run task asynchronously."""
        tool_logs = []
        
        def tool_callback(tool_name: str, elapsed: float):
            log_line = f"tool: {tool_name} ({elapsed:.1f}s)"
            tool_logs.append(log_line)
            # Update status with tool log
            self.status_bar.set_message(log_line)
        
        try:
            if task_type == TaskType.EXPLAIN:
                registry.execute("ai-explain", code, filename, instruction, callback)
            elif task_type == TaskType.REFACTOR:
                registry.execute("ai-refactor", code, filename, None, callback)
            elif task_type == TaskType.FIX_ERROR:
                registry.execute("ai-fix", code, filename, instruction, callback)
            elif task_type == TaskType.ADD_TESTS:
                registry.execute("ai-tests", [filename], {"code": code}, callback)
            elif task_type == TaskType.FIX_TESTS:
                # For fix tests, we need test output context
                test_output = run_tests()  # Run tests to get current status
                context = {
                    "test_output": test_output,
                    "code": code,
                    "filename": filename
                }
                registry.execute("ai-fix-tests", context, callback, tool_callback)
        except Exception as e:
            self.output_text += f"\nError: {e}"
            self.output_area.text = self.output_text
        finally:
            completion()

    def show_diff_viewer(self):
        """Show the enhanced diff viewer."""
        active_buffer = self.buffer_manager.active()
        if not active_buffer:
            return

        text_by_path = {str(active_buffer.path): active_buffer.text}

        # Show the diff viewer (this will block until user makes a choice)
        updated_texts = show_diff_viewer(self.diff_text, text_by_path)

        if updated_texts:
            # Apply the changes
            for path, new_text in updated_texts.items():
                self.buffer_manager.update_text(path, new_text)
            self.status_bar.set_message("Diff applied")
        else:
            self.status_bar.set_message("Diff discarded")

        self.has_diff = False
        self.diff_text = ""


class QuickOpenDialog:
    """Quick-open file dialog."""

    def __init__(self, buffer_manager: BufferManager):
        self.buffer_manager = buffer_manager
        self.visible = False
        self.query = ""
        self.files = get_project_files()
        self.filtered_files = self.files[:10]

        self.input_buffer = Buffer()
        self.results_control = FormattedTextControl(text=self._format_results())

    def get_layout(self):
        """Get dialog layout."""
        return ConditionalContainer(
            Dialog(
                title="Quick Open",
                body=HSplit([
                    Window(BufferControl(self.input_buffer), height=1),
                    Window(self.results_control, height=10)
                ]),
                buttons=[]
            ),
            filter=self.visible
        )

    def show(self):
        """Show the dialog."""
        self.visible = True
        self.query = ""
        self.input_buffer.text = ""
        self._update_results()

    def hide(self):
        """Hide the dialog."""
        self.visible = False

    def update_query(self):
        """Update search query."""
        self.query = self.input_buffer.text
        self._update_results()

    def select_file(self, index: int):
        """Select a file from results."""
        if index < len(self.filtered_files):
            file_path = self.filtered_files[index]
            full_path = Path.cwd() / file_path
            self.buffer_manager.open(full_path)
            self.hide()

    def _update_results(self):
        """Update filtered results."""
        if not self.query:
            self.filtered_files = self.files[:10]
        else:
            results = fuzzy_search_files(self.query, self.files, 10)
            self.filtered_files = [path for path, _ in results]

        self.results_control.text = self._format_results()

    def _format_results(self) -> FormattedText:
        """Format results for display."""
        lines = []
        for i, file in enumerate(self.filtered_files):
            lines.append((f"[{i}] {file}", ""))
        return FormattedText(lines)


class GitMenuDialog:
    """Git operations menu."""

    def __init__(self, buffer_manager: BufferManager, status_bar: StatusBar):
        self.buffer_manager = buffer_manager
        self.status_bar = status_bar
        self.visible = False
        self.options = [
            ("Status", self.show_status),
            ("Diff", self.show_diff),
            ("Stage", self.stage_file),
            ("Commit", self.commit_changes)
        ]
        self.selected_index = 0

        self.control = FormattedTextControl(
            text=self._format_menu(),
            focusable=True
        )

    def get_layout(self):
        """Get dialog layout."""
        return ConditionalContainer(
            Dialog(
                title="Git Menu",
                body=Window(self.control, height=6),
                buttons=[]
            ),
            filter=self.visible
        )

    def show(self):
        """Show the menu."""
        self.visible = True
        self.selected_index = 0
        self.control.text = self._format_menu()

    def hide(self):
        """Hide the menu."""
        self.visible = False

    def select_option(self, index: int):
        """Select an option."""
        if 0 <= index < len(self.options):
            self.options[index][1]()
            self.hide()

    def show_status(self):
        """Show git status."""
        result = registry.execute("git-status")
        self.status_bar.set_message(result)

    def show_diff(self):
        """Show git diff."""
        active = self.buffer_manager.active()
        path = str(active.path) if active and active.path else None
        result = registry.execute("git-diff", path)
        self.status_bar.set_message("Diff shown (placeholder)")

    def stage_file(self):
        """Stage current file."""
        active = self.buffer_manager.active()
        path = str(active.path) if active and active.path else None
        result = registry.execute("git-stage", path)
        self.status_bar.set_message(result)

    def commit_changes(self):
        """Commit changes (placeholder for now)."""
        self.status_bar.set_message("Commit: enter message in command line")

    def _format_menu(self) -> FormattedText:
        """Format menu for display."""
        lines = []
        for i, (name, _) in enumerate(self.options):
            marker = ">" if i == self.selected_index else " "
            lines.append((f"{marker} {name}", ""))
        return FormattedText(lines)


class FileTreePanel:
    """File tree sidebar."""

    def __init__(self, buffer_manager: BufferManager):
        self.buffer_manager = buffer_manager
        self.visible = False
        self.tree_lines = self._build_tree()

        self.control = FormattedTextControl(
            text=FormattedText(self.tree_lines),
            focusable=True
        )

    def get_layout(self):
        """Get panel layout."""
        return ConditionalContainer(
            Window(self.control, width=30),
            filter=self.visible
        )

    def toggle(self):
        """Toggle panel visibility."""
        self.visible = not self.visible

    def _build_tree(self) -> FormattedText:
        """Build tree display."""
        tree = get_directory_tree(Path.cwd())
        lines = flatten_tree_for_display(tree)
        return FormattedText([(line, "") for line in lines])


class DiagnosticsPane:
    """Diagnostics information pane."""

    def __init__(self, diagnostics_manager: LSPDiagnosticsManager, buffer_manager: BufferManager):
        self.diagnostics_manager = diagnostics_manager
        self.buffer_manager = buffer_manager
        self.visible = True  # Always visible but can be toggled
        self.current_message = ""

        self.control = FormattedTextControl(text=self._get_text())

    def get_layout(self):
        """Get panel layout."""
        return ConditionalContainer(
            Window(self.control, height=2),
            filter=self.visible
        )

    def update_for_cursor(self, line_number: int):
        """Update diagnostics for current cursor line."""
        active = self.buffer_manager.active()
        if active and active.path:
            tooltip = self.diagnostics_manager.overlay.get_hover_tooltip(str(active.path), line_number)
            self.current_message = tooltip or ""
        else:
            self.current_message = ""
        self.control.text = self._get_text()

    def _get_text(self) -> str:
        """Get the text to display."""
        if self.current_message:
            return f"Diagnostics: {self.current_message}"
        return "No diagnostics"


def create_app():
    """Create the editor application."""
    buffer_manager = BufferManager()
    status_bar = StatusBar()
    ai_panel = AIPanel(buffer_manager, status_bar)
    quick_open = QuickOpenDialog(buffer_manager)
    file_tree = FileTreePanel(buffer_manager)
    git_gutter = GitStatusGutter()
    git_menu = GitMenuDialog(buffer_manager, status_bar)
    diagnostics_manager = LSPDiagnosticsManager()
    diagnostics_pane = DiagnosticsPane(diagnostics_manager, buffer_manager)

    # Initialize LSP handler
    from editor.lsp_actions import lsp_handler
    lsp_handler.__init__(buffer_manager, status_bar)  # Re-initialize with proper instances
    # Register LSP clients
    for lang, client in diagnostics_manager.clients.items():
        lsp_handler.register_client(lang, client)

    # Initialize quick fix manager
    quick_fix = QuickFixManager(buffer_manager, lsp_handler)

    # Initialize plugin system
    from plugins import plugin_manager
    config = get_config()
    if config.plugins_enabled:
        plugin_manager.set_safe_mode(config.plugins_safe_mode)
        # Load auto-load plugins
        for plugin_name in config.plugins_auto_load:
            plugin_manager.load_plugin(plugin_name)

    # Initialize telemetry
    telemetry.track_event("app_started", {"version": "0.1.0"})

    # Create main buffer
    main_buffer = Buffer()

    # Status bar
    status_bar = StatusBar()

    # Layout
    layout = Layout(
        HSplit([
            VSplit([
                file_tree.get_layout(),
                Window(BufferControl(main_buffer)),
                ai_panel.get_layout(),
            ]),
            diagnostics_pane.get_layout(),
            quick_open.get_layout(),
            git_menu.get_layout(),
            quick_fix.get_layout(),
            Window(status_bar.control, height=1)
        ])
    )

    kb = KeyBindings()

    # Basic navigation
    @kb.add('c-q')
    def quit_app(event):
        """Quit the application."""
        event.app.exit()

    @kb.add('c-o')
    def open_file(event):
        """Open file (placeholder)."""
        main_buffer.text = "# Example Python file\nprint('Hello, World!')\n"
        status_bar.set_message("File opened (placeholder)")

    # AI panel
    @kb.add('alt-a')
    def toggle_ai_panel(event):
        """Toggle AI panel."""
        ai_panel.toggle()

    @kb.add('c-r')
    def run_ai_task(event):
        """Run AI task."""
        ai_panel.run_task()

    # Quick open
    @kb.add('c-p')
    def show_quick_open(event):
        """Show quick open dialog."""
        quick_open.show()

    @kb.add('escape')
    def hide_quick_open(event):
        """Hide quick open dialog."""
        if quick_open.visible:
            quick_open.hide()
        elif ai_panel.visible:
            ai_panel.toggle()
        elif git_menu.visible:
            git_menu.hide()
        elif quick_fix.dialog.visible:
            quick_fix.hide()

    @kb.add('enter')
    def quick_open_select(event):
        """Select file in quick open."""
        if quick_open.visible:
            # For simplicity, select first result
            quick_open.select_file(0)
        elif git_menu.visible:
            git_menu.select_option(git_menu.selected_index)
        elif quick_fix.dialog.visible:
            quick_fix.dialog._apply_selected()

    @kb.add('up')
    def menu_up(event):
        """Navigate menu up."""
        if git_menu.visible:
            git_menu.selected_index = max(0, git_menu.selected_index - 1)
            git_menu.control.text = git_menu._format_menu()
        elif quick_fix.dialog.visible:
            quick_fix.dialog.select_prev()

    @kb.add('down')
    def menu_down(event):
        """Navigate menu down."""
        if git_menu.visible:
            git_menu.selected_index = min(len(git_menu.options) - 1, git_menu.selected_index + 1)
            git_menu.control.text = git_menu._format_menu()
        elif quick_fix.dialog.visible:
            quick_fix.dialog.select_next()

    # File tree
    @kb.add('c-b')
    def toggle_file_tree(event):
        """Toggle file tree."""
        file_tree.toggle()

    # Git menu
    @kb.add('alt-g')
    def show_git_menu(event):
        """Show Git menu."""
        git_menu.show()

    # AI commands
    @kb.add('c-e')
    def ai_explain_cmd(event):
        """AI explain command."""
        ai_panel.task_selector.current_value = "explain"
        ai_panel.run_task()

    @kb.add('c-f')
    def ai_refactor_cmd(event):
        """AI refactor command."""
        ai_panel.task_selector.current_value = "refactor"
        ai_panel.run_task()

    @kb.add('c-t')
    def ai_fix_tests_cmd(event):
        """AI fix tests command."""
        ai_panel.task_selector.current_value = "fix_tests"
        ai_panel.run_task()

    # Diagnostics
    @kb.add('alt-d')
    def toggle_diagnostics(event):
        """Toggle diagnostics overlay."""
        diagnostics_manager.overlay.toggle()
        status_bar.set_message(f"Diagnostics {'enabled' if diagnostics_manager.overlay.enabled else 'disabled'}")

    # LSP actions
    @kb.add('f1')
    def lsp_hover_cmd(event):
        """LSP hover."""
        registry.execute("lsp-hover")

    @kb.add('f12')
    def lsp_definition_cmd(event):
        """LSP go to definition."""
        registry.execute("lsp-definition")

    @kb.add('s-f12')
    def lsp_references_cmd(event):
        """LSP find references."""
        registry.execute("lsp-references")

    @kb.add('f2')
    def lsp_rename_cmd(event):
        """LSP rename."""
        # This would need input dialog
        status_bar.set_message("Rename: Enter new name in command line")

    @kb.add('a-s-f')
    def lsp_format_cmd(event):
        """LSP format document."""
        registry.execute("lsp-format")

    @kb.add('alt-o')
    def lsp_organize_imports_cmd(event):
        """LSP organize imports."""
        registry.execute("lsp-organize-imports")

    @kb.add('alt-.')
    def lsp_quick_fix_cmd(event):
        """LSP quick fix."""
        telemetry.track_feature_usage("lsp_quick_fix")
        quick_fix.show_quick_fix()

    @kb.add('a-s-f')
    def ws_format_cmd(event):
        """Workspace format."""
        telemetry.track_feature_usage("workspace_format")
        result = registry.execute("ws-refactor-format")
        status_bar.set_message(result)

    @kb.add('a-s-o')
    def ws_organize_imports_cmd(event):
        """Workspace organize imports."""
        telemetry.track_feature_usage("workspace_organize_imports")
        result = registry.execute("ws-refactor-organize-imports")
        status_bar.set_message(result)

    # Plan commands
    @kb.add('alt-p')
    def show_plan_viewer_cmd(event):
        """Show plan viewer (placeholder)."""
        status_bar.set_message("Plan viewer: Select plan first")

    @kb.add('alt-w')
    def plan_playground_cmd(event):
        """Plan playground mode."""
        # This would need to get the current plan ID from somewhere
        status_bar.set_message("Playground: Select plan first")

    # Git extras
    @kb.add('alt-b')
    def git_blame_cmd(event):
        """Git blame for current line."""
        result = registry.execute("git-blame")
        status_bar.set_message(result)

    @kb.add('a-s-g')
    def git_branch_switcher_cmd(event):
        """Git branch switcher."""
        result = registry.execute("git-branch-switcher")
        status_bar.set_message(result)

    style = Style.from_dict({
        'status': 'bg:#444444 #ffffff',
    })

    return Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=True
    )


if __name__ == "__main__":
    # Run telemetry wizard if needed
    telemetry_choice = run_telemetry_wizard()
    if telemetry_choice is not None:
        print(f"Telemetry {'enabled' if telemetry_choice else 'disabled'}")

    app = create_app()
    app.run()