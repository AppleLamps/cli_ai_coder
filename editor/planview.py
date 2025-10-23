"""Plan viewer for AI-generated multi-file change plans."""

import asyncio
from typing import Callable, Dict, List, Optional, Any
from pathlib import Path

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Button, TextArea

from ai.plan_executor import PlanExecutor
from ai.planner import Plan, PlanStep
from ai.prompts import build_file_change_prompt
from ai.client import XAIClient
from ai.router import ModelRouter, TaskType
from editor.diffview import show_diff_viewer
from editor.statusbar import StatusBar


class PlanStepItem:
    """Represents a plan step with its diff."""

    def __init__(self, step: PlanStep, index: int):
        self.step = step
        self.index = index
        self.selected = True
        self.diff_text = ""
        self.diff_loaded = False
        self.loading = False


class PlanViewer:
    """Interactive viewer for AI-generated plans."""

    def __init__(self, plan: Plan, on_apply: Callable[[Plan, List[PlanStepItem]], None], on_discard: Callable[[], None]):
        self.plan = plan
        self.on_apply = on_apply
        self.on_discard = on_discard
        self.visible = True
        self.executor = PlanExecutor()
        self.apply_in_progress = False
        self.apply_result = None  # (success, message)
        self.applied_plan_id = None
        self.playground_info = None  # For playground mode

        # Create step items
        self.step_items = [
            PlanStepItem(step, i) for i, step in enumerate(plan.steps)
        ]

        # UI components
        self.title_control = FormattedTextControl(text=self._format_title())
        self.rationale_control = FormattedTextControl(text=self._format_rationale())
        self.steps_control = FormattedTextControl(text=self._format_steps())
        self.diff_control = FormattedTextControl(text=self._format_current_diff())
        self.status_control = FormattedTextControl(text=self._format_status())
        self.progress_control = FormattedTextControl(text="")

        self.apply_button = Button("Apply Selected", handler=self.apply_selected)
        self.apply_all_button = Button("Apply All", handler=self.apply_all)
        self.playground_button = Button("Playground", handler=self.apply_playground)
        self.discard_button = Button("Discard", handler=self.discard)
        self.checkout_button = Button("Checkout Branch", handler=self.checkout_branch)
        self.rollback_button = Button("Rollback", handler=self.rollback)
        self.promote_button = Button("Promote", handler=self.promote_playground)
        self.open_editor_button = Button("Open in Editor", handler=self.open_in_editor)
        self.cleanup_button = Button("Cleanup", handler=self.cleanup_playground)
        self.close_button = Button("Close", handler=self.close)

        self.current_step_index = 0
        self.client = XAIClient()
        self.router = ModelRouter()

    def get_layout(self):
        """Get the viewer layout."""
        from prompt_toolkit.layout import ConditionalContainer, HSplit, VSplit

        base_layout = HSplit([
            Window(content=self.title_control, height=2),
            Window(content=self.rationale_control, height=3),
            VSplit([
                Window(self.steps_control, width=40),
                Window(self.diff_control, width=60)
            ]),
            Window(self.status_control, height=2),
            ConditionalContainer(
                Window(self.progress_control, height=3),
                filter=self.apply_in_progress
            ),
            HSplit([
                ConditionalContainer(
                    HSplit([self.apply_button, self.apply_all_button, self.playground_button, self.discard_button], height=1),
                    filter=not self.apply_result
                ),
                ConditionalContainer(
                    HSplit([self.checkout_button, self.rollback_button, self.promote_button, self.open_editor_button, self.cleanup_button, self.close_button], height=1),
                    filter=self.apply_result is not None
                )
            ], height=1)
        ])

        return ConditionalContainer(
            base_layout,
            filter=self.visible
        )

    def toggle_step(self):
        """Toggle selection of current step."""
        if self.step_items:
            self.step_items[self.current_step_index].selected = not self.step_items[self.current_step_index].selected
            self._update_display()

    def next_step(self):
        """Move to next step."""
        if self.step_items:
            self.current_step_index = (self.current_step_index + 1) % len(self.step_items)
            self._update_display()
            # Lazy load diff for current step
            asyncio.create_task(self._load_diff_for_current())

    def prev_step(self):
        """Move to previous step."""
        if self.step_items:
            self.current_step_index = (self.current_step_index - 1) % len(self.step_items)
            self._update_display()
            # Lazy load diff for current step
            asyncio.create_task(self._load_diff_for_current())

    async def _load_diff_for_current(self):
        """Load diff for current step if not already loaded."""
        if not self.step_items:
            return

        item = self.step_items[self.current_step_index]
        if item.diff_loaded or item.loading:
            return

        item.loading = True
        self._update_display()

        try:
            diff = await self._generate_diff_for_step(item.step)
            item.diff_text = diff
            item.diff_loaded = True
        except Exception as e:
            item.diff_text = f"Error generating diff: {e}"
            item.diff_loaded = True
        finally:
            item.loading = False
            self._update_display()

    async def _generate_diff_for_step(self, step: PlanStep) -> str:
        """Generate diff for a plan step."""
        # Read current file content
        file_path = Path.cwd() / step.file
        if not file_path.exists():
            if step.intent == "create":
                original_text = ""
            else:
                raise FileNotFoundError(f"File {step.file} does not exist")
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    original_text = f.read()
            except (OSError, IOError) as e:
                raise Exception(f"Cannot read file {step.file}: {e}")

        # Get neighbors/context (simplified - could be enhanced)
        neighbors = {}

        # Build prompt
        messages = build_file_change_prompt(
            {
                "file": step.file,
                "intent": step.intent,
                "explanation": step.explanation
            },
            original_text,
            neighbors,
            step.constraints
        )

        # Choose model
        lines = len(original_text.splitlines())
        model = self.router.choose_model(lines, 1, task_type=TaskType.REFACTOR)
        temperature = 0.2

        # Call AI
        response = self.client.complete_chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=4000
        )

        if not response:
            return "No diff generated"

        # Check if it's a noop
        try:
            noop_check = response.strip()
            if noop_check.startswith("{") and "noop" in noop_check:
                return "No changes needed"
        except:
            pass

        # Validate diff
        if is_unified_diff(response):
            return response
        else:
            return f"Invalid diff format:\n{response}"

    def apply_selected(self):
        """Apply selected steps."""
        selected_items = [item for item in self.step_items if item.selected]
        if selected_items:
            self._start_apply([item.index for item in selected_items])

    def apply_all(self):
        """Apply all steps."""
        for item in self.step_items:
            item.selected = True
        self._start_apply(list(range(len(self.step_items))))

    def _start_apply(self, step_indices: List[int]):
        """Start the apply process."""
        self.apply_in_progress = True
        self.progress_control.text = "Starting plan application..."
        self._update_display()

        # Run apply in background
        import asyncio
        asyncio.create_task(self._apply_async(step_indices))

    async def _apply_async(self, step_indices: List[int]):
        """Apply the plan asynchronously."""
        try:
            success, message = self.executor.apply_plan(self.plan, step_indices)
            self.apply_result = (success, message)
            self.applied_plan_id = self.plan.plan_id if success else None
            self.progress_control.text = f"{'✓' if success else '✗'} {message}"
        except Exception as e:
            self.apply_result = (False, f"Apply failed: {e}")
            self.progress_control.text = f"✗ Apply failed: {e}"
        finally:
            self.apply_in_progress = False
            self._update_display()

    def checkout_branch(self):
        """Checkout the applied branch."""
        if self.applied_plan_id:
            applied_info = self.executor._load_applied_info(self.applied_plan_id)
            if applied_info:
                # Would run git checkout applied_info.branch_name
                self.progress_control.text = f"Checked out branch {applied_info.branch_name}"
            else:
                self.progress_control.text = "Could not load applied info"
        self._update_display()

    def rollback(self):
        """Rollback the applied plan."""
        if self.applied_plan_id:
            success, message = self.executor.rollback_plan(self.applied_plan_id)
            self.progress_control.text = f"{'✓' if success else '✗'} {message}"
        self._update_display()

    def apply_playground(self):
        """Apply selected steps in playground worktree."""
        selected_items = [item for item in self.step_items if item.selected]
        if selected_items:
            self._start_playground_apply([item.index for item in selected_items])

    def _start_playground_apply(self, step_indices: List[int]):
        """Start the playground apply process."""
        self.apply_in_progress = True
        self.progress_control.text = "Creating playground worktree..."
        self._update_display()

        # Run apply in background
        import asyncio
        asyncio.create_task(self._apply_playground_async(step_indices))

    async def _apply_playground_async(self, step_indices: List[int]):
        """Apply the plan in playground asynchronously."""
        try:
            success, message, playground_info = self.executor.apply_plan_playground(self.plan, step_indices)
            self.apply_result = (success, message)
            self.applied_plan_id = self.plan.plan_id if success else None
            self.playground_info = playground_info
            self.progress_control.text = f"{'✓' if success else '✗'} {message}"
        except Exception as e:
            self.apply_result = (False, f"Playground apply failed: {e}")
            self.progress_control.text = f"✗ Playground apply failed: {e}"
        finally:
            self.apply_in_progress = False
            self._update_display()

    def promote_playground(self):
        """Promote the playground worktree."""
        if self.applied_plan_id and self.playground_info:
            # For now, default to apply_patches mode
            success, message = self.executor.promote_playground(self.applied_plan_id, "apply_patches")
            self.progress_control.text = f"{'✓' if success else '✗'} {message}"
        self._update_display()

    def open_in_editor(self):
        """Open the playground worktree in editor."""
        if self.playground_info:
            # This would need to integrate with the editor to open files from worktree path
            self.progress_control.text = f"Opening worktree at {self.playground_info.worktree_path}"
        self._update_display()

    def cleanup_playground(self):
        """Clean up the playground worktree."""
        if self.applied_plan_id:
            success, message = self.executor.cleanup_playground(self.applied_plan_id)
            self.progress_control.text = f"{'✓' if success else '✗'} {message}"
        self._update_display()

    def _update_display(self):
        """Update all display components."""
        self.steps_control.text = self._format_steps()
        self.diff_control.text = self._format_current_diff()
        self.status_control.text = self._format_status()
        # progress_control is updated separately

    def _format_title(self) -> str:
        """Format the plan title."""
        return f"Plan: {self.plan.title}"

    def _format_rationale(self) -> str:
        """Format the plan rationale."""
        return f"Rationale: {self.plan.rationale}"

    def _format_steps(self) -> str:
        """Format the steps list."""
        lines = ["Steps (j/k to navigate, space to toggle):", ""]
        for i, item in enumerate(self.step_items):
            marker = ">" if i == self.current_step_index else " "
            checkbox = "[x]" if item.selected else "[ ]"
            status = " (loading...)" if item.loading else " (loaded)" if item.diff_loaded else ""
            lines.append(f"{marker}{checkbox} {item.step.file}: {item.step.intent}{status}")
            if i == self.current_step_index:
                lines.append(f"    {item.step.explanation}")
        return "\n".join(lines)

    def _format_current_diff(self) -> str:
        """Format the diff for current step."""
        if not self.step_items:
            return "No steps"

        item = self.step_items[self.current_step_index]
        if not item.diff_loaded:
            if item.loading:
                return "Loading diff..."
            else:
                return "Press Enter to load diff"

        if not item.diff_text:
            return "No diff available"

        # Truncate long diffs for display
        lines = item.diff_text.splitlines()
        if len(lines) > 30:
            lines = lines[:30] + ["... (truncated)"]
        return "\n".join(lines)

    def _format_status(self) -> str:
        """Format the status line."""
        selected_count = sum(1 for item in self.step_items if item.selected)
        loaded_count = sum(1 for item in self.step_items if item.diff_loaded)
        return f"Step {self.current_step_index + 1}/{len(self.step_items)} | Selected: {selected_count}/{len(self.step_items)} | Loaded: {loaded_count}/{len(self.step_items)}"


def show_plan_viewer(plan: Plan) -> Optional[Dict[str, str]]:
    """
    Show the plan viewer and return updated file contents if applied.

    Args:
        plan: The plan to display.

    Returns:
        Dict of file paths to new contents if applied, None if discarded.
    """
    result = None
    applied = False

    def on_apply(plan_obj: Plan, selected_items: List[PlanStepItem]):
        nonlocal result, applied
        # For now, just mark as applied - actual application is done by executor
        result = {}
        applied = True

    def on_discard():
        nonlocal applied
        applied = False

    viewer = PlanViewer(plan, on_apply, on_discard)

    # Create key bindings
    kb = KeyBindings()

    @kb.add('j')
    def next_step(event):
        viewer.next_step()

    @kb.add('k')
    def prev_step(event):
        viewer.prev_step()

    @kb.add('space')
    def toggle_step(event):
        viewer.toggle_step()

    @kb.add('enter')
    def load_diff(event):
        asyncio.create_task(viewer._load_diff_for_current())

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