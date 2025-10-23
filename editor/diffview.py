"""Enhanced diff viewer with side-by-side display and partial hunk application."""

from typing import Callable, Dict, List, Optional

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Button

from ai.patches import apply_unified_diff, parse_affected_paths


class Hunk:
    """Represents a diff hunk."""

    def __init__(self, filename: str, start_line: int, content: str, selected: bool = False):
        self.filename = filename
        self.start_line = start_line
        self.content = content
        self.selected = selected


def split_hunks(diff: str) -> List[Hunk]:
    """
    Split a unified diff into individual hunks.

    Args:
        diff: The unified diff string.

    Returns:
        List of Hunk objects.
    """
    hunks = []
    lines = diff.splitlines()
    i = 0

    while i < len(lines):
        if lines[i].startswith('+++ '):
            filename = lines[i][4:].strip()
            if filename.startswith('b/'):
                filename = filename[2:]
            i += 1

            # Skip to first hunk
            while i < len(lines) and not lines[i].startswith('@@'):
                i += 1

            while i < len(lines) and lines[i].startswith('@@'):
                # Parse hunk header
                match = __import__('re').match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', lines[i])
                if match:
                    old_start = int(match.group(1))
                    new_start = int(match.group(3))

                    # Collect hunk content
                    i += 1
                    hunk_lines = []
                    while i < len(lines) and not lines[i].startswith('@@') and not lines[i].startswith('+++'):
                        hunk_lines.append(lines[i])
                        i += 1

                    hunk_content = '\n'.join(hunk_lines)
                    hunks.append(Hunk(filename, new_start, hunk_content))
                else:
                    i += 1
        else:
            i += 1

    return hunks


def apply_selected_hunks(text_by_path: Dict[str, str], hunks: List[Hunk]) -> Dict[str, str]:
    """
    Apply only the selected hunks to the texts.

    Args:
        text_by_path: Dict of filename to current content.
        hunks: List of hunks to apply (only selected ones will be applied).

    Returns:
        Dict of filename to updated content.
    """
    # Group hunks by filename
    hunks_by_file = {}
    for hunk in hunks:
        if hunk.selected:
            if hunk.filename not in hunks_by_file:
                hunks_by_file[hunk.filename] = []
            hunks_by_file[hunk.filename].append(hunk)

    updated = text_by_path.copy()

    for filename, file_hunks in hunks_by_file.items():
        if filename not in updated:
            continue

        # Sort hunks by line number
        file_hunks.sort(key=lambda h: h.start_line)

        # Apply hunks in order (this is simplified - real implementation would need proper diff application)
        current_text = updated[filename]
        lines = current_text.splitlines()

        for hunk in file_hunks:
            # This is a simplified application - in practice, you'd need to parse the hunk properly
            # For now, we'll just replace the content around the start line
            hunk_lines = hunk.content.splitlines()
            added_lines = [line[1:] for line in hunk_lines if line.startswith('+')]
            removed_lines = [line[1:] for line in hunk_lines if line.startswith('-')]

            # Simple replacement logic (very basic)
            start_idx = hunk.start_line - 1
            if start_idx < len(lines):
                # Remove old lines and add new ones
                end_idx = start_idx + len(removed_lines)
                lines = lines[:start_idx] + added_lines + lines[end_idx:]

        updated[filename] = '\n'.join(lines)

    return updated


class DiffViewer:
    """Side-by-side diff viewer with hunk selection."""

    def __init__(self, diff_text: str, on_apply: Callable, on_discard: Callable):
        self.diff_text = diff_text
        self.on_apply = on_apply
        self.on_discard = on_discard
        self.hunks = split_hunks(diff_text)
        self.current_hunk_idx = 0
        self.visible = True

        # UI components
        self.left_panel = FormattedTextControl(text=self._format_left_panel())
        self.right_panel = FormattedTextControl(text=self._format_right_panel())
        self.status_label = FormattedTextControl(text=self._format_status())

        self.apply_button = Button("Apply Selected", handler=self.apply_selected)
        self.apply_all_button = Button("Apply All", handler=self.apply_all)
        self.discard_button = Button("Discard", handler=self.discard)

    def get_layout(self):
        """Get the viewer layout."""
        from prompt_toolkit.layout import ConditionalContainer

        return ConditionalContainer(
            HSplit([
                Window(content=FormattedTextControl(text="Diff Viewer (j/k to navigate, space to toggle, enter to apply)"), height=1),
                VSplit([
                    Window(self.left_panel, width=50),
                    Window(self.right_panel, width=50)
                ]),
                Window(self.status_label, height=1),
                HSplit([
                    self.apply_button,
                    self.apply_all_button,
                    self.discard_button
                ], height=1)
            ]),
            filter=self.visible
        )

    def toggle_hunk(self):
        """Toggle selection of current hunk."""
        if self.hunks:
            self.hunks[self.current_hunk_idx].selected = not self.hunks[self.current_hunk_idx].selected
            self._update_display()

    def next_hunk(self):
        """Move to next hunk."""
        if self.hunks:
            self.current_hunk_idx = (self.current_hunk_idx + 1) % len(self.hunks)
            self._update_display()

    def prev_hunk(self):
        """Move to previous hunk."""
        if self.hunks:
            self.current_hunk_idx = (self.current_hunk_idx - 1) % len(self.hunks)
            self._update_display()

    def apply_selected(self):
        """Apply only selected hunks."""
        selected_hunks = [h for h in self.hunks if h.selected]
        self.on_apply(selected_hunks)
        self.visible = False

    def apply_all(self):
        """Apply all hunks."""
        for hunk in self.hunks:
            hunk.selected = True
        self.on_apply(self.hunks)
        self.visible = False

    def discard(self):
        """Discard the diff."""
        self.on_discard()
        self.visible = False

    def _update_display(self):
        """Update the display."""
        self.left_panel.text = self._format_left_panel()
        self.right_panel.text = self._format_right_panel()
        self.status_label.text = self._format_status()

    def _format_left_panel(self) -> str:
        """Format the left panel (original)."""
        if not self.hunks:
            return "No hunks found"

        lines = []
        for i, hunk in enumerate(self.hunks):
            marker = "[x]" if hunk.selected else "[ ]"
            if i == self.current_hunk_idx:
                marker = f"[{marker[1]}]"  # Highlight current
            lines.append(f"{marker} Hunk {i+1}: {hunk.filename}:{hunk.start_line}")
            # Show a few lines of context
            hunk_preview = hunk.content.replace('\n', ' | ')[:100]
            lines.append(f"    {hunk_preview}...")

        return '\n'.join(lines)

    def _format_right_panel(self) -> str:
        """Format the right panel (changes)."""
        if not self.hunks:
            return ""

        hunk = self.hunks[self.current_hunk_idx]
        lines = [f"File: {hunk.filename}", f"Line: {hunk.start_line}", ""]
        lines.extend(hunk.content.splitlines()[:20])  # Show first 20 lines
        if len(hunk.content.splitlines()) > 20:
            lines.append("... (truncated)")
        return '\n'.join(lines)

    def _format_status(self) -> str:
        """Format the status line."""
        if not self.hunks:
            return "No hunks to display"

        selected_count = sum(1 for h in self.hunks if h.selected)
        return f"Hunk {self.current_hunk_idx + 1}/{len(self.hunks)} | Selected: {selected_count}/{len(self.hunks)}"


def show_diff_viewer(diff_text: str, text_by_path: Dict[str, str]) -> Optional[Dict[str, str]]:
    """
    Show the diff viewer and return updated texts if applied.

    Args:
        diff_text: The unified diff.
        text_by_path: Current file contents.

    Returns:
        Updated file contents if applied, None if discarded.
    """
    result = None
    applied = False

    def on_apply(hunks):
        nonlocal result, applied
        result = apply_selected_hunks(text_by_path, hunks)
        applied = True

    def on_discard():
        nonlocal applied
        applied = False

    viewer = DiffViewer(diff_text, on_apply, on_discard)

    # Create a simple key-binding app for the viewer
    kb = KeyBindings()

    @kb.add('j')
    def next_hunk(event):
        viewer.next_hunk()

    @kb.add('k')
    def prev_hunk(event):
        viewer.prev_hunk()

    @kb.add('space')
    def toggle_hunk(event):
        viewer.toggle_hunk()

    @kb.add('enter')
    def apply_selected(event):
        viewer.apply_selected()

    @kb.add('a')
    def apply_all(event):
        viewer.apply_all()

    @kb.add('d')
    def discard(event):
        viewer.discard()

    @kb.add('q')
    def quit_viewer(event):
        viewer.discard()
        event.app.exit()

    style = Style.from_dict({
        'status': 'bg:#444444 #ffffff',
    })

    app = Application(
        layout=Layout(viewer.get_layout()),
        key_bindings=kb,
        style=style,
        full_screen=False
    )

    app.run()

    return result if applied else None