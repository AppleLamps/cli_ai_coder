"""Configuration loading."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None


@dataclass(frozen=True)
class Config:
    """Application configuration."""
    api_key_env: str
    model_default: str
    theme: str
    tab_width: int
    soft_wrap: bool
    # Tool and safety settings
    allow_tool_run_tests: bool
    max_tool_calls: int
    redact_patterns: List[str]
    # Metrics settings
    show_metrics: bool
    metrics_window: int
    # Git settings
    git_enabled: bool
    # LSP settings
    lsp_enabled: bool
    lsp_python_cmd: str
    lsp_semantics_enabled: bool
    lsp_semantics_debounce_ms: int
    # History settings
    history_enabled: bool
    history_max_entries: int
    # Provider settings
    provider: str
    # Billing settings
    billing_monthly_budget_usd: float
    billing_soft_limit_ratio: float
    billing_hard_stop: bool
    # Inline suggest settings
    inline_suggest_enabled: bool
    inline_suggest_idle_ms: int
    inline_suggest_max_chars: int
    inline_suggest_model: str
    # Index settings
    index_enabled: bool
    index_use_embeddings: bool
    index_model: str
    index_max_chunks: int
    index_embeddings_model: str
    index_chunk_tokens: int
    index_chunk_overlap: int
    index_max_bytes: int
    index_ignored_globs: List[str]
    index_watch_enabled: bool
    index_watch_debounce_ms: int
    index_watch_polling_fallback: bool
    index_watch_polling_interval_ms: int
    # Network settings
    network_max_retries: int
    network_base_delay_ms: int
    network_backoff_multiplier: float
    network_jitter_ratio: float
    network_circuit_fail_threshold: int
    network_circuit_window_sec: int
    network_circuit_cooldown_sec: int
    network_offline: bool
    network_request_timeout_sec: int
    # Retrieval settings
    retrieval_reranker: str
    retrieval_rerank_top_k: int
    # Pipeline settings
    pipeline_verify_tests: bool
    # Planner settings
    planner_enabled: bool
    planner_max_files: int
    planner_max_total_changed_lines: int
    planner_require_green_tests: bool
    planner_branch_prefix: str
    planner_autostash: bool
    planner_checkpoint_commit_per_file: bool
    planner_keep_branch_on_rollback: bool
    planner_preflight_show_summary: bool
    # Playground settings
    playground_enabled: bool
    playground_root: str
    playground_promote_branch_prefix: str
    playground_keep_worktree_on_promote: bool
    # Plugin settings
    plugins_enabled: bool
    plugins_safe_mode: bool
    plugins_auto_load: List[str]
    plugins_sandbox_enabled: bool
    plugins_default_timeout: float
    plugins_memory_limit_mb: int
    # Codemod settings
    codemods_enabled: bool
    codemods_max_files: int
    codemods_max_total_changed_lines: int
    # Telemetry settings
    telemetry_enabled: bool
    telemetry_user_id: str


DEFAULT_CONFIG = Config(
    api_key_env="XAI_API_KEY",
    model_default="grok-code-fast-1",
    theme="native",
    tab_width=4,
    soft_wrap=False,
    allow_tool_run_tests=True,
    max_tool_calls=3,
    redact_patterns=["API_KEY", "SECRET", "TOKEN", "PASSWORD"],
    show_metrics=True,
    metrics_window=5,
    git_enabled=True,
    lsp_enabled=True,
    lsp_python_cmd="pylsp",
    lsp_semantics_enabled=True,
    lsp_semantics_debounce_ms=150,
    history_enabled=True,
    history_max_entries=1000,
    provider="xai",
    billing_monthly_budget_usd=5.0,
    billing_soft_limit_ratio=0.8,
    billing_hard_stop=False,
    inline_suggest_enabled=True,
    inline_suggest_idle_ms=800,
    inline_suggest_max_chars=120,
    inline_suggest_model="grok-code-fast-1",
    index_enabled=True,
    index_use_embeddings=False,
    index_model="all-MiniLM-L6-v2",
    index_max_chunks=5000,
    index_embeddings_model="sentence-transformers/all-MiniLM-L6-v2",
    index_chunk_tokens=400,
    index_chunk_overlap=60,
    index_max_bytes=800000,
    index_ignored_globs=["**/.git/**", "**/node_modules/**", "**/dist/**", "**/build/**", "**/.venv/**"],
    index_watch_enabled=True,
    index_watch_debounce_ms=100,
    index_watch_polling_fallback=True,
    index_watch_polling_interval_ms=1500,
    network_max_retries=3,
    network_base_delay_ms=200,
    network_backoff_multiplier=2.0,
    network_jitter_ratio=0.3,
    network_circuit_fail_threshold=5,
    network_circuit_window_sec=60,
    network_circuit_cooldown_sec=60,
    network_offline=False,
    network_request_timeout_sec=60,
    retrieval_reranker="bm25",
    retrieval_rerank_top_k=50,
    pipeline_verify_tests=True,
    planner_enabled=True,
    planner_max_files=20,
    planner_max_total_changed_lines=800,
    planner_require_green_tests=False,
    planner_branch_prefix="ai/plan-",
    planner_autostash=True,
    planner_checkpoint_commit_per_file=True,
    planner_keep_branch_on_rollback=False,
    planner_preflight_show_summary=True,
    playground_enabled=True,
    playground_root=".cli_ai_coder/worktrees",
    playground_promote_branch_prefix="ai/promoted/",
    playground_keep_worktree_on_promote=False,
    plugins_enabled=True,
    plugins_safe_mode=True,
    plugins_auto_load=[],
    plugins_sandbox_enabled=True,
    plugins_default_timeout=5.0,
    plugins_memory_limit_mb=100,
    codemods_enabled=True,
    codemods_max_files=200,
    codemods_max_total_changed_lines=5000,
    telemetry_enabled=False,
    telemetry_user_id=""
)


def get_config() -> Config:
    """
    Load configuration from ~/.cli_ai_coder.toml if present, else use defaults.

    Returns:
        The loaded configuration.
    """
    config_path = Path.home() / ".cli_ai_coder.toml"

    if not config_path.exists():
        return DEFAULT_CONFIG

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        return Config(
            api_key_env=data.get("api_key_env", DEFAULT_CONFIG.api_key_env),
            model_default=data.get("model_default", DEFAULT_CONFIG.model_default),
            theme=data.get("theme", DEFAULT_CONFIG.theme),
            tab_width=data.get("tab_width", DEFAULT_CONFIG.tab_width),
            soft_wrap=data.get("soft_wrap", DEFAULT_CONFIG.soft_wrap),
            allow_tool_run_tests=data.get("allow_tool_run_tests", DEFAULT_CONFIG.allow_tool_run_tests),
            max_tool_calls=data.get("max_tool_calls", DEFAULT_CONFIG.max_tool_calls),
            redact_patterns=data.get("redact_patterns", DEFAULT_CONFIG.redact_patterns),
            show_metrics=data.get("show_metrics", DEFAULT_CONFIG.show_metrics),
            metrics_window=data.get("metrics_window", DEFAULT_CONFIG.metrics_window),
            git_enabled=data.get("git", {}).get("enabled", DEFAULT_CONFIG.git_enabled),
            lsp_enabled=data.get("lsp", {}).get("enabled", DEFAULT_CONFIG.lsp_enabled),
            lsp_python_cmd=data.get("lsp", {}).get("python", {}).get("cmd", DEFAULT_CONFIG.lsp_python_cmd),
    lsp_semantics_enabled=data.get("lsp", {}).get("semantics", {}).get("enabled", DEFAULT_CONFIG.lsp_semantics_enabled),
    lsp_semantics_debounce_ms=data.get("lsp", {}).get("semantics", {}).get("debounce_ms", DEFAULT_CONFIG.lsp_semantics_debounce_ms),
            history_enabled=data.get("history", {}).get("enabled", DEFAULT_CONFIG.history_enabled),
            history_max_entries=data.get("history", {}).get("max_entries", DEFAULT_CONFIG.history_max_entries),
            provider=data.get("ai", {}).get("provider", DEFAULT_CONFIG.provider),
            billing_monthly_budget_usd=data.get("billing", {}).get("monthly_budget_usd", DEFAULT_CONFIG.billing_monthly_budget_usd),
            billing_soft_limit_ratio=data.get("billing", {}).get("soft_limit_ratio", DEFAULT_CONFIG.billing_soft_limit_ratio),
            billing_hard_stop=data.get("billing", {}).get("hard_stop", DEFAULT_CONFIG.billing_hard_stop),
            inline_suggest_enabled=data.get("inline_suggest", {}).get("enabled", DEFAULT_CONFIG.inline_suggest_enabled),
            inline_suggest_idle_ms=data.get("inline_suggest", {}).get("idle_ms", DEFAULT_CONFIG.inline_suggest_idle_ms),
            inline_suggest_max_chars=data.get("inline_suggest", {}).get("max_chars", DEFAULT_CONFIG.inline_suggest_max_chars),
            inline_suggest_model=data.get("inline_suggest", {}).get("model", DEFAULT_CONFIG.inline_suggest_model),
            index_enabled=data.get("index", {}).get("enabled", DEFAULT_CONFIG.index_enabled),
            index_use_embeddings=data.get("index", {}).get("use_embeddings", DEFAULT_CONFIG.index_use_embeddings),
            index_model=data.get("index", {}).get("model", DEFAULT_CONFIG.index_model),
            index_max_chunks=data.get("index", {}).get("max_chunks", DEFAULT_CONFIG.index_max_chunks),
            index_embeddings_model=data.get("index", {}).get("embeddings_model", DEFAULT_CONFIG.index_embeddings_model),
            index_chunk_tokens=data.get("index", {}).get("chunk_tokens", DEFAULT_CONFIG.index_chunk_tokens),
            index_chunk_overlap=data.get("index", {}).get("chunk_overlap", DEFAULT_CONFIG.index_chunk_overlap),
            index_max_bytes=data.get("index", {}).get("max_bytes", DEFAULT_CONFIG.index_max_bytes),
            index_ignored_globs=data.get("index", {}).get("ignored_globs", DEFAULT_CONFIG.index_ignored_globs),
            index_watch_enabled=data.get("index", {}).get("watch", {}).get("enabled", DEFAULT_CONFIG.index_watch_enabled),
            index_watch_debounce_ms=data.get("index", {}).get("watch", {}).get("debounce_ms", DEFAULT_CONFIG.index_watch_debounce_ms),
            index_watch_polling_fallback=data.get("index", {}).get("watch", {}).get("polling_fallback", DEFAULT_CONFIG.index_watch_polling_fallback),
            index_watch_polling_interval_ms=data.get("index", {}).get("watch", {}).get("polling_interval_ms", DEFAULT_CONFIG.index_watch_polling_interval_ms),
            network_max_retries=data.get("network", {}).get("max_retries", DEFAULT_CONFIG.network_max_retries),
            network_base_delay_ms=data.get("network", {}).get("base_delay_ms", DEFAULT_CONFIG.network_base_delay_ms),
            network_backoff_multiplier=data.get("network", {}).get("backoff_multiplier", DEFAULT_CONFIG.network_backoff_multiplier),
            network_jitter_ratio=data.get("network", {}).get("jitter_ratio", DEFAULT_CONFIG.network_jitter_ratio),
            network_circuit_fail_threshold=data.get("network", {}).get("circuit_fail_threshold", DEFAULT_CONFIG.network_circuit_fail_threshold),
            network_circuit_window_sec=data.get("network", {}).get("circuit_window_sec", DEFAULT_CONFIG.network_circuit_window_sec),
            network_circuit_cooldown_sec=data.get("network", {}).get("circuit_cooldown_sec", DEFAULT_CONFIG.network_circuit_cooldown_sec),
            network_offline=data.get("network", {}).get("offline", DEFAULT_CONFIG.network_offline),
            network_request_timeout_sec=data.get("network", {}).get("request_timeout_sec", DEFAULT_CONFIG.network_request_timeout_sec),
            retrieval_reranker=data.get("retrieval", {}).get("reranker", DEFAULT_CONFIG.retrieval_reranker),
            retrieval_rerank_top_k=data.get("retrieval", {}).get("rerank_top_k", DEFAULT_CONFIG.retrieval_rerank_top_k),
            pipeline_verify_tests=data.get("pipeline", {}).get("verify_tests", DEFAULT_CONFIG.pipeline_verify_tests),
            planner_enabled=data.get("planner", {}).get("enabled", DEFAULT_CONFIG.planner_enabled),
            planner_max_files=data.get("planner", {}).get("max_files", DEFAULT_CONFIG.planner_max_files),
            planner_max_total_changed_lines=data.get("planner", {}).get("max_total_changed_lines", DEFAULT_CONFIG.planner_max_total_changed_lines),
            planner_require_green_tests=data.get("planner", {}).get("require_green_tests", DEFAULT_CONFIG.planner_require_green_tests),
            planner_branch_prefix=data.get("planner", {}).get("branch_prefix", DEFAULT_CONFIG.planner_branch_prefix),
            planner_autostash=data.get("planner", {}).get("autostash", DEFAULT_CONFIG.planner_autostash),
            planner_checkpoint_commit_per_file=data.get("planner", {}).get("checkpoint_commit_per_file", DEFAULT_CONFIG.planner_checkpoint_commit_per_file),
            planner_keep_branch_on_rollback=data.get("planner", {}).get("keep_branch_on_rollback", DEFAULT_CONFIG.planner_keep_branch_on_rollback),
            planner_preflight_show_summary=data.get("planner", {}).get("preflight_show_summary", DEFAULT_CONFIG.planner_preflight_show_summary),
            playground_enabled=data.get("playground", {}).get("enabled", DEFAULT_CONFIG.playground_enabled),
            playground_root=data.get("playground", {}).get("root", DEFAULT_CONFIG.playground_root),
            playground_promote_branch_prefix=data.get("playground", {}).get("promote_branch_prefix", DEFAULT_CONFIG.playground_promote_branch_prefix),
            playground_keep_worktree_on_promote=data.get("playground", {}).get("keep_worktree_on_promote", DEFAULT_CONFIG.playground_keep_worktree_on_promote),
            plugins_enabled=data.get("plugins", {}).get("enabled", DEFAULT_CONFIG.plugins_enabled),
            plugins_safe_mode=data.get("plugins", {}).get("safe_mode", DEFAULT_CONFIG.plugins_safe_mode),
            plugins_auto_load=data.get("plugins", {}).get("auto_load", DEFAULT_CONFIG.plugins_auto_load),
            plugins_sandbox_enabled=data.get("plugins", {}).get("sandbox_enabled", DEFAULT_CONFIG.plugins_sandbox_enabled),
            plugins_default_timeout=data.get("plugins", {}).get("default_timeout", DEFAULT_CONFIG.plugins_default_timeout),
            plugins_memory_limit_mb=data.get("plugins", {}).get("memory_limit_mb", DEFAULT_CONFIG.plugins_memory_limit_mb),
            codemods_enabled=data.get("codemods", {}).get("enabled", DEFAULT_CONFIG.codemods_enabled),
            codemods_max_files=data.get("codemods", {}).get("max_files", DEFAULT_CONFIG.codemods_max_files),
            codemods_max_total_changed_lines=data.get("codemods", {}).get("max_total_changed_lines", DEFAULT_CONFIG.codemods_max_total_changed_lines),
            telemetry_enabled=data.get("telemetry", {}).get("enabled", DEFAULT_CONFIG.telemetry_enabled),
            telemetry_user_id=data.get("telemetry", {}).get("user_id", DEFAULT_CONFIG.telemetry_user_id)
        )
    except Exception:
        # If loading fails, return defaults
        return DEFAULT_CONFIG


def save_config(config: Config) -> None:
    """
    Save configuration to ~/.cli_ai_coder.toml.

    Args:
        config: The configuration to save.
    """
    if tomli_w is None:
        raise ImportError("tomli_w is required to save configuration")

    config_path = Path.home() / ".cli_ai_coder.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert config to dict for TOML serialization
    config_dict = {
        "api_key_env": config.api_key_env,
        "model_default": config.model_default,
        "theme": config.theme,
        "tab_width": config.tab_width,
        "soft_wrap": config.soft_wrap,
        "allow_tool_run_tests": config.allow_tool_run_tests,
        "max_tool_calls": config.max_tool_calls,
        "redact_patterns": config.redact_patterns,
        "show_metrics": config.show_metrics,
        "metrics_window": config.metrics_window,
        "git": {
            "enabled": config.git_enabled
        },
        "lsp": {
            "enabled": config.lsp_enabled,
            "python": {
                "cmd": config.lsp_python_cmd
            },
            "semantics": {
                "enabled": config.lsp_semantics_enabled,
                "debounce_ms": config.lsp_semantics_debounce_ms
            }
        },
        "history": {
            "enabled": config.history_enabled,
            "max_entries": config.history_max_entries
        },
        "ai": {
            "provider": config.provider
        },
        "billing": {
            "monthly_budget_usd": config.billing_monthly_budget_usd,
            "soft_limit_ratio": config.billing_soft_limit_ratio,
            "hard_stop": config.billing_hard_stop
        },
        "inline_suggest": {
            "enabled": config.inline_suggest_enabled,
            "idle_ms": config.inline_suggest_idle_ms,
            "max_chars": config.inline_suggest_max_chars,
            "model": config.inline_suggest_model
        },
        "index": {
            "enabled": config.index_enabled,
            "use_embeddings": config.index_use_embeddings,
            "model": config.index_model,
            "max_chunks": config.index_max_chunks,
            "embeddings_model": config.index_embeddings_model,
            "chunk_tokens": config.index_chunk_tokens,
            "chunk_overlap": config.index_chunk_overlap,
            "max_bytes": config.index_max_bytes,
            "ignored_globs": config.index_ignored_globs,
            "watch": {
                "enabled": config.index_watch_enabled,
                "debounce_ms": config.index_watch_debounce_ms,
                "polling_fallback": config.index_watch_polling_fallback,
                "polling_interval_ms": config.index_watch_polling_interval_ms
            }
        },
        "network": {
            "max_retries": config.network_max_retries,
            "base_delay_ms": config.network_base_delay_ms,
            "backoff_multiplier": config.network_backoff_multiplier,
            "jitter_ratio": config.network_jitter_ratio,
            "circuit_fail_threshold": config.network_circuit_fail_threshold,
            "circuit_window_sec": config.network_circuit_window_sec,
            "cooldown_sec": config.network_circuit_cooldown_sec,
            "offline": config.network_offline,
            "request_timeout_sec": config.network_request_timeout_sec
        },
        "retrieval": {
            "reranker": config.retrieval_reranker,
            "rerank_top_k": config.retrieval_rerank_top_k
        },
        "pipeline": {
            "verify_tests": config.pipeline_verify_tests
        },
        "planner": {
            "enabled": config.planner_enabled,
            "max_files": config.planner_max_files,
            "max_total_changed_lines": config.planner_max_total_changed_lines,
            "require_green_tests": config.planner_require_green_tests,
            "branch_prefix": config.planner_branch_prefix,
            "autostash": config.planner_autostash,
            "checkpoint_commit_per_file": config.planner_checkpoint_commit_per_file,
            "keep_branch_on_rollback": config.planner_keep_branch_on_rollback,
            "preflight_show_summary": config.planner_preflight_show_summary
        },
        "playground": {
            "enabled": config.playground_enabled,
            "root": config.playground_root,
            "promote_branch_prefix": config.playground_promote_branch_prefix,
            "keep_worktree_on_promote": config.playground_keep_worktree_on_promote
        },
        "plugins": {
            "enabled": config.plugins_enabled,
            "safe_mode": config.plugins_safe_mode,
            "auto_load": config.plugins_auto_load,
            "sandbox_enabled": config.plugins_sandbox_enabled,
            "default_timeout": config.plugins_default_timeout,
            "memory_limit_mb": config.plugins_memory_limit_mb
        },
        "codemods": {
            "enabled": config.codemods_enabled,
            "max_files": config.codemods_max_files,
            "max_total_changed_lines": config.codemods_max_total_changed_lines
        },
        "telemetry": {
            "enabled": config.telemetry_enabled,
            "user_id": config.telemetry_user_id
        }
    }

    with open(config_path, "wb") as f:
        tomli_w.dump(config_dict, f)