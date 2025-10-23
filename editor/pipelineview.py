"""Pipeline view for spec→tests→code workflow."""

from typing import Optional

from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.widgets import Button, TextArea
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from ai.spec_pipeline import SpecPipeline, Spec, TestSuite, Implementation, PipelineStage
from ai.client import XAIClient
from ai.router import ModelRouter


class PipelineView:
    """Interactive view for spec→tests→code pipeline."""

    def __init__(self, user_description: str):
        self.user_description = user_description
        self.pipeline = SpecPipeline(XAIClient(), ModelRouter())
        self.current_stage = PipelineStage.SPEC
        self.spec: Optional[Spec] = None
        self.test_suite: Optional[TestSuite] = None
        self.implementation: Optional[Implementation] = None
        self.error_message: Optional[str] = None
        self.in_progress = False

        # UI components
        self.title_control = FormattedTextControl(text=self._format_title())
        self.status_control = FormattedTextControl(text=self._format_status())
        self.content_control = FormattedTextControl(text=self._format_content())
        self.progress_control = FormattedTextControl(text="")

        self.run_button = Button("Run Pipeline", handler=self.run_pipeline)
        self.run_spec_button = Button("Generate Spec", handler=self.run_spec)
        self.run_tests_button = Button("Generate Tests", handler=self.run_tests)
        self.run_code_button = Button("Generate Code", handler=self.run_code)
        self.close_button = Button("Close", handler=self.close)

    def get_layout(self):
        """Get the pipeline view layout."""
        return HSplit([
            Window(content=self.title_control, height=2),
            Window(content=self.status_control, height=2),
            Window(content=self.content_control, height=15),
            Window(content=self.progress_control, height=3),
            HSplit([
                self.run_button,
                self.run_spec_button,
                self.run_tests_button,
                self.run_code_button,
                self.close_button
            ], height=1)
        ])

    def run_pipeline(self):
        """Run the complete pipeline."""
        if self.in_progress:
            return

        self.in_progress = True
        self.error_message = None
        self.progress_control.text = "Running complete pipeline..."
        self._update_display()

        # Run in background
        import asyncio
        asyncio.create_task(self._run_pipeline_async())

    async def _run_pipeline_async(self):
        """Run the pipeline asynchronously."""
        try:
            self.current_stage = PipelineStage.SPEC
            self._update_display()

            spec, tests, impl = self.pipeline.run_pipeline(self.user_description)
            self.spec = spec
            self.test_suite = tests
            self.implementation = impl
            self.current_stage = PipelineStage.VERIFY
            self.progress_control.text = "Pipeline completed successfully!"
        except Exception as e:
            self.error_message = str(e)
            self.progress_control.text = f"Pipeline failed: {e}"
        finally:
            self.in_progress = False
            self._update_display()

    def run_spec(self):
        """Generate specification only."""
        if self.in_progress:
            return

        self.in_progress = True
        self.error_message = None
        self.progress_control.text = "Generating specification..."
        self._update_display()

        import asyncio
        asyncio.create_task(self._run_spec_async())

    async def _run_spec_async(self):
        """Generate spec asynchronously."""
        try:
            self.spec = self.pipeline.generate_spec(self.user_description)
            self.current_stage = PipelineStage.SPEC
            self.progress_control.text = "Specification generated successfully!"
        except Exception as e:
            self.error_message = str(e)
            self.progress_control.text = f"Spec generation failed: {e}"
        finally:
            self.in_progress = False
            self._update_display()

    def run_tests(self):
        """Generate tests from spec."""
        if not self.spec or self.in_progress:
            return

        self.in_progress = True
        self.error_message = None
        self.progress_control.text = "Generating test suite..."
        self._update_display()

        import asyncio
        asyncio.create_task(self._run_tests_async())

    async def _run_tests_async(self):
        """Generate tests asynchronously."""
        try:
            if self.spec:
                self.test_suite = self.pipeline.generate_tests(self.spec)
                self.current_stage = PipelineStage.TESTS
                self.progress_control.text = "Test suite generated successfully!"
            else:
                self.progress_control.text = "No specification available"
        except Exception as e:
            self.error_message = str(e)
            self.progress_control.text = f"Test generation failed: {e}"
        finally:
            self.in_progress = False
            self._update_display()

    def run_code(self):
        """Generate code from spec and tests."""
        if not self.spec or not self.test_suite or self.in_progress:
            return

        self.in_progress = True
        self.error_message = None
        self.progress_control.text = "Generating implementation..."
        self._update_display()

        import asyncio
        asyncio.create_task(self._run_code_async())

    async def _run_code_async(self):
        """Generate code asynchronously."""
        try:
            if self.spec and self.test_suite:
                self.implementation = self.pipeline.generate_code(self.spec, self.test_suite)
                self.current_stage = PipelineStage.CODE
                self.progress_control.text = "Implementation generated successfully!"
            else:
                self.progress_control.text = "Specification and test suite required"
        except Exception as e:
            self.error_message = str(e)
            self.progress_control.text = f"Code generation failed: {e}"
        finally:
            self.in_progress = False
            self._update_display()

    def close(self):
        """Close the pipeline view."""
        # This will be handled by the key binding
        pass

    def _update_display(self):
        """Update all display components."""
        self.status_control.text = self._format_status()
        self.content_control.text = self._format_content()

    def _format_title(self) -> str:
        """Format the title."""
        return f"Spec→Tests→Code Pipeline: {self.user_description[:50]}..."

    def _format_status(self) -> str:
        """Format the status line."""
        stage_names = {
            PipelineStage.SPEC: "Specification",
            PipelineStage.TESTS: "Test Generation",
            PipelineStage.CODE: "Code Generation",
            PipelineStage.VERIFY: "Verification"
        }

        status = f"Stage: {stage_names[self.current_stage]}"

        if self.spec:
            status += " | ✓ Spec"
        if self.test_suite:
            status += " | ✓ Tests"
        if self.implementation:
            status += " | ✓ Code"

        if self.error_message:
            status += " | ✗ Error"

        return status

    def _format_content(self) -> str:
        """Format the main content area."""
        if self.error_message:
            return f"Error:\n{self.error_message}"

        lines = []

        if self.spec:
            lines.append("Specification:")
            lines.append(f"  Title: {self.spec.title}")
            lines.append(f"  Requirements: {len(self.spec.requirements)}")
            lines.append(f"  Acceptance Criteria: {len(self.spec.acceptance_criteria)}")
            lines.append("")

        if self.test_suite:
            lines.append("Test Suite:")
            lines.append(f"  Files: {len(self.test_suite.files)}")
            lines.append(f"  Coverage Goals: {len(self.test_suite.coverage_goals)}")
            lines.append("")

        if self.implementation:
            lines.append("Implementation:")
            lines.append(f"  Files: {len(self.implementation.files)}")
            lines.append(f"  Summary: {self.implementation.changes_summary}")
            lines.append("")

        if not any([self.spec, self.test_suite, self.implementation]):
            lines.append("No pipeline results yet.")
            lines.append("")
            lines.append("Use the buttons above to generate spec, tests, and code,")
            lines.append("or run the complete pipeline.")

        return "\n".join(lines)


def show_pipeline_view(user_description: str) -> Optional[dict]:
    """
    Show the pipeline view for spec→tests→code workflow.

    Args:
        user_description: The user's feature description.

    Returns:
        Dict with pipeline results if completed, None if cancelled.
    """
    view = PipelineView(user_description)

    # Key bindings
    kb = KeyBindings()

    @kb.add('q')
    @kb.add('c-c')
    def quit_view(event):
        event.app.exit()

    @kb.add('r')
    def run_pipeline_key(event):
        view.run_pipeline()

    @kb.add('s')
    def run_spec_key(event):
        view.run_spec()

    @kb.add('t')
    def run_tests_key(event):
        view.run_tests()

    @kb.add('c')
    def run_code_key(event):
        view.run_code()

    style = Style.from_dict({
        'status': 'bg:#444444 #ffffff',
    })

    app = Application(
        layout=Layout(view.get_layout()),
        key_bindings=kb,
        style=style,
        full_screen=False
    )

    app.run()

    # Return results if pipeline completed
    if view.spec and view.test_suite and view.implementation:
        return {
            "spec": view.spec.to_dict(),
            "tests": view.test_suite.to_dict(),
            "implementation": view.implementation.to_dict()
        }

    return None