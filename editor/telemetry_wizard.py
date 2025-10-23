"""Telemetry opt-in wizard."""

from pathlib import Path
from typing import Callable

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Button, Dialog, Label, RadioList

from core.config import get_config, save_config, Config
from core.telemetry import telemetry


class TelemetryWizard:
    """Wizard for telemetry opt-in on first run."""

    def __init__(self, on_complete: Callable[[bool], None]):
        self.on_complete = on_complete
        self.choice = None

        # Check if this is first run
        config_file = Path.home() / ".cli_ai_coder" / "config.toml"
        self.is_first_run = not config_file.exists()

        if not self.is_first_run:
            # Check if telemetry choice already made
            config = get_config()
            if config.telemetry_enabled is not None:
                self.on_complete(config.telemetry_enabled)
                return

        self.visible = self.is_first_run

        self.radio_list = RadioList([
            ("yes", "Yes, help improve CLI AI Coder"),
            ("no", "No, keep my usage private")
        ])

        self.dialog = Dialog(
            title="Welcome to CLI AI Coder!",
            body=HSplit([
                Label(text="Help us improve CLI AI Coder by enabling anonymous usage analytics."),
                Label(text=""),
                Label(text="We collect:"),
                Label(text="• Feature usage statistics"),
                Label(text="• Error reports (no code content)"),
                Label(text="• Performance metrics"),
                Label(text=""),
                Label(text="All data is anonymous and cannot be used to identify you."),
                Label(text="You can change this setting anytime in the configuration."),
                Label(text=""),
                self.radio_list
            ]),
            buttons=[
                Button(text="Continue", handler=self._on_continue),
                Button(text="Learn More", handler=self._on_learn_more)
            ]
        )

    def get_layout(self):
        """Get the wizard layout."""
        return self.dialog if self.visible else Window()

    def _on_continue(self):
        """Handle continue button."""
        choice = self.radio_list.current_value
        enabled = choice == "yes"

        # Get current config and create new one with telemetry settings
        current_config = get_config()
        new_config = Config(
            api_key_env=current_config.api_key_env,
            model_default=current_config.model_default,
            theme=current_config.theme,
            tab_width=current_config.tab_width,
            soft_wrap=current_config.soft_wrap,
            allow_tool_run_tests=current_config.allow_tool_run_tests,
            max_tool_calls=current_config.max_tool_calls,
            redact_patterns=current_config.redact_patterns,
            show_metrics=current_config.show_metrics,
            metrics_window=current_config.metrics_window,
            git_enabled=current_config.git_enabled,
            lsp_enabled=current_config.lsp_enabled,
            lsp_python_cmd=current_config.lsp_python_cmd,
            lsp_semantics_enabled=current_config.lsp_semantics_enabled,
            lsp_semantics_debounce_ms=current_config.lsp_semantics_debounce_ms,
            history_enabled=current_config.history_enabled,
            history_max_entries=current_config.history_max_entries,
            provider=current_config.provider,
            billing_monthly_budget_usd=current_config.billing_monthly_budget_usd,
            billing_soft_limit_ratio=current_config.billing_soft_limit_ratio,
            billing_hard_stop=current_config.billing_hard_stop,
            inline_suggest_enabled=current_config.inline_suggest_enabled,
            inline_suggest_idle_ms=current_config.inline_suggest_idle_ms,
            inline_suggest_max_chars=current_config.inline_suggest_max_chars,
            inline_suggest_model=current_config.inline_suggest_model,
            index_enabled=current_config.index_enabled,
            index_use_embeddings=current_config.index_use_embeddings,
            index_model=current_config.index_model,
            index_max_chunks=current_config.index_max_chunks,
            index_embeddings_model=current_config.index_embeddings_model,
            index_chunk_tokens=current_config.index_chunk_tokens,
            index_chunk_overlap=current_config.index_chunk_overlap,
            index_max_bytes=current_config.index_max_bytes,
            index_ignored_globs=current_config.index_ignored_globs,
            index_watch_enabled=current_config.index_watch_enabled,
            index_watch_debounce_ms=current_config.index_watch_debounce_ms,
            index_watch_polling_fallback=current_config.index_watch_polling_fallback,
            index_watch_polling_interval_ms=current_config.index_watch_polling_interval_ms,
            network_max_retries=current_config.network_max_retries,
            network_base_delay_ms=current_config.network_base_delay_ms,
            network_backoff_multiplier=current_config.network_backoff_multiplier,
            network_jitter_ratio=current_config.network_jitter_ratio,
            network_circuit_fail_threshold=current_config.network_circuit_fail_threshold,
            network_circuit_window_sec=current_config.network_circuit_window_sec,
            network_circuit_cooldown_sec=current_config.network_circuit_cooldown_sec,
            network_offline=current_config.network_offline,
            network_request_timeout_sec=current_config.network_request_timeout_sec,
            retrieval_reranker=current_config.retrieval_reranker,
            retrieval_rerank_top_k=current_config.retrieval_rerank_top_k,
            pipeline_verify_tests=current_config.pipeline_verify_tests,
            planner_enabled=current_config.planner_enabled,
            planner_max_files=current_config.planner_max_files,
            planner_max_total_changed_lines=current_config.planner_max_total_changed_lines,
            planner_require_green_tests=current_config.planner_require_green_tests,
            planner_branch_prefix=current_config.planner_branch_prefix,
            planner_autostash=current_config.planner_autostash,
            planner_checkpoint_commit_per_file=current_config.planner_checkpoint_commit_per_file,
            planner_keep_branch_on_rollback=current_config.planner_keep_branch_on_rollback,
            planner_preflight_show_summary=current_config.planner_preflight_show_summary,
            playground_enabled=current_config.playground_enabled,
            playground_root=current_config.playground_root,
            playground_promote_branch_prefix=current_config.playground_promote_branch_prefix,
            playground_keep_worktree_on_promote=current_config.playground_keep_worktree_on_promote,
            plugins_enabled=current_config.plugins_enabled,
            plugins_safe_mode=current_config.plugins_safe_mode,
            plugins_auto_load=current_config.plugins_auto_load,
            telemetry_enabled=enabled,
            telemetry_user_id=current_config.telemetry_user_id
        )

        # Save the new config
        save_config(new_config)

        # Update telemetry manager
        if enabled:
            telemetry.enable()
        else:
            telemetry.disable()

        self.visible = False
        self.on_complete(enabled)

    def _on_learn_more(self):
        """Handle learn more button."""
        # For now, just show a message. In future, could open browser
        pass

    def show(self):
        """Show the wizard."""
        if self.is_first_run:
            self.visible = True

    def hide(self):
        """Hide the wizard."""
        self.visible = False


def run_telemetry_wizard() -> bool:
    """Run the telemetry wizard and return the user's choice."""
    result = None

    def on_complete(enabled: bool):
        nonlocal result
        result = enabled

    wizard = TelemetryWizard(on_complete)

    if wizard.visible:
        # Create a simple app to show the wizard
        kb = KeyBindings()

        @kb.add('escape')
        def cancel(event):
            wizard.hide()
            event.app.exit()

        style = Style.from_dict({
            'dialog': 'bg:#444444',
            'dialog.body': 'bg:#333333 #ffffff',
            'dialog.shadow': 'bg:#000000',
        })

        app = Application(
            layout=Layout(wizard.get_layout()),
            key_bindings=kb,
            style=style,
            full_screen=False
        )

        app.run()

    return result if result is not None else False