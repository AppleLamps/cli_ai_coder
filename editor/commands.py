"""Command registry and keybindings."""

import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ai.client import XAIClient
from ai.prompts import (
    build_add_tests_prompt,
    build_explain_prompt,
    build_fix_error_prompt,
    build_fix_tests_prompt,
    build_refactor_prompt
)
from ai.router import ModelRouter, TaskType
from ai.tools import read_file, repo_search, run_tests


class CommandRegistry:
    """Registry for editor commands."""

    def __init__(self) -> None:
        self.commands: Dict[str, Callable[..., Any]] = {}
        self.client = XAIClient()
        self.router = ModelRouter()
        # Register tools
        self.client.register_tool("repo_search", repo_search)
        self.client.register_tool("run_tests", run_tests)
        self.client.register_tool("read_file", read_file)

    def register(self, name: str, func: Callable[..., Any]) -> None:
        """
        Register a command.

        Args:
            name: Command name.
            func: Command function.
        """
        self.commands[name] = func

    def execute(self, name: str, *args, **kwargs) -> Any:
        """
        Execute a command.

        Args:
            name: Command name.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Command result.
        """
        if name in self.commands:
            return self.commands[name](*args, **kwargs)
        raise ValueError(f"Unknown command: {name}")

    def run_ai_task(
        self,
        task_type: TaskType,
        code: str,
        filename: str,
        question: Optional[str] = None,
        constraints: Optional[Dict] = None,
        traceback: Optional[str] = None,
        context: Optional[Dict] = None,
        callback: Optional[Callable[[str], None]] = None,
        enable_tools: bool = False,
        tool_callback: Optional[Callable[[str, float], None]] = None
    ) -> str:
        """
        Run an AI task.

        Args:
            task_type: Type of task.
            code: Code content.
            filename: Filename.
            question: Optional question for explain.
            constraints: Optional constraints for refactor.
            traceback: Optional traceback for fix_error.
            context: Optional context for add_tests.
            callback: Optional streaming callback.
            enable_tools: Whether to enable tool calling.

        Returns:
            AI response.
        """
        # Build messages based on task type
        if task_type == TaskType.EXPLAIN:
            messages = build_explain_prompt(filename, code, question)
        elif task_type == TaskType.REFACTOR:
            messages = build_refactor_prompt(filename, code, constraints)
        elif task_type == TaskType.FIX_ERROR:
            messages = build_fix_error_prompt(filename, code, traceback or "")
        elif task_type == TaskType.ADD_TESTS:
            messages = build_add_tests_prompt([filename], context or {})
        elif task_type == TaskType.FIX_TESTS:
            messages = build_fix_tests_prompt(context or {})
        else:
            raise ValueError(f"Unknown task type: {task_type}")

        # Choose model
        lines = len(code.splitlines())
        model = self.router.choose_model(lines, 1, task_type=task_type)
        temperature = self.router.get_temperature(model)

        # Call AI
        return self.client.complete_chat(
            model=model,
            messages=messages,
            temperature=temperature,
            callback=callback,
            enable_tools=enable_tools,
            tool_callback=tool_callback,
            task_type=task_type.value if hasattr(task_type, 'value') else str(task_type),
            input_files=[filename] if filename else [],
            applied_patch=False  # Will be updated when patch is applied
        )


# Global registry instance
registry = CommandRegistry()

# Register AI commands
def ai_explain(code: str, filename: str, question: Optional[str] = None, callback: Optional[Callable[[str], None]] = None) -> str:
    """Explain code."""
    return registry.run_ai_task(TaskType.EXPLAIN, code, filename, question=question, callback=callback)

def ai_refactor(code: str, filename: str, constraints: Optional[Dict] = None, callback: Optional[Callable[[str], None]] = None) -> str:
    """Refactor code."""
    return registry.run_ai_task(TaskType.REFACTOR, code, filename, constraints=constraints, callback=callback)

def ai_fix_error(code: str, filename: str, traceback: str, callback: Optional[Callable[[str], None]] = None) -> str:
    """Fix error in code."""
    return registry.run_ai_task(TaskType.FIX_ERROR, code, filename, traceback=traceback, callback=callback)

def ai_add_tests(targets: list, context: Dict, callback: Optional[Callable[[str], None]] = None) -> str:
    """Add tests."""
    # For simplicity, use the first target as filename
    filename = targets[0] if targets else "unknown"
    code = context.get("code", "")
    return registry.run_ai_task(TaskType.ADD_TESTS, code, filename, context=context, callback=callback)

def ai_fix_tests(context: Dict, callback: Optional[Callable[[str], None]] = None, tool_callback: Optional[Callable[[str, float], None]] = None) -> str:
    """Fix failing tests."""
    # Run with tools enabled
    code = context.get("code", "")
    filename = context.get("filename", "unknown")
    return registry.run_ai_task(TaskType.FIX_TESTS, code, filename, context=context, callback=callback, enable_tools=True, tool_callback=tool_callback)

# Git commands
def git_status() -> str:
    """Show git status summary."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            if not lines:
                return "Working directory clean"
            
            # Group by status
            staged = []
            unstaged = []
            untracked = []
            
            for line in lines:
                status = line[:2]
                filename = line[3:]
                if status[0] != ' ':
                    staged.append(f"{status[0]} {filename}")
                if status[1] != ' ':
                    unstaged.append(f"{status[1]} {filename}")
                if status == '??':
                    untracked.append(filename)
            
            output = []
            if staged:
                output.append("Staged changes:")
                output.extend(f"  {item}" for item in staged)
            if unstaged:
                output.append("Unstaged changes:")
                output.extend(f"  {item}" for item in unstaged)
            if untracked:
                output.append("Untracked files:")
                output.extend(f"  {item}" for item in untracked)
            
            return "\n".join(output)
        else:
            return f"Git status failed: {result.stderr}"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "Git not available or not a git repository"

def git_diff(path: Optional[str] = None) -> str:
    """Show git diff for file or all changes."""
    try:
        cmd = ["git", "diff"]
        if path:
            cmd.extend(["--", path])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        if result.returncode == 0:
            diff = result.stdout.strip()
            return diff if diff else "No changes"
        else:
            return f"Git diff failed: {result.stderr}"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "Git not available"

def git_stage(path: Optional[str] = None) -> str:
    """Stage file or all changes."""
    try:
        cmd = ["git", "add"]
        if path:
            cmd.append(path)
        else:
            cmd.append(".")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        if result.returncode == 0:
            return f"Staged {'all changes' if not path else path}"
        else:
            return f"Git add failed: {result.stderr}"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "Git not available"

def git_unstage(path: Optional[str] = None) -> str:
    """Unstage file or all changes."""
    try:
        cmd = ["git", "reset", "HEAD"]
        if path:
            cmd.append(path)
        else:
            cmd.append("--")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        if result.returncode == 0:
            return f"Unstaged {'all changes' if not path else path}"
        else:
            return f"Git reset failed: {result.stderr}"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "Git not available"

def git_commit(message: str) -> str:
    """Commit staged changes."""
    if not message.strip():
        return "Commit message cannot be empty"
    
    try:
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        if result.returncode == 0:
            # Extract commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=Path.cwd()
            )
            if hash_result.returncode == 0:
                short_hash = hash_result.stdout.strip()[:7]
                return f"Committed as {short_hash}"
            else:
                return "Committed successfully"
        else:
            return f"Git commit failed: {result.stderr}"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "Git not available"

# AI History commands
def ai_history() -> str:
    """Show AI interaction history."""
    from ai.history import history
    
    entries = history.get_entries(limit=10)  # Show last 10
    if not entries:
        return "No AI history available"
    
    lines = ["AI Interaction History (most recent first):", ""]
    for i, entry in enumerate(entries, 1):
        timestamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.timestamp))
        task = entry.task_type
        model = entry.model
        tokens = sum(entry.token_metrics.values())
        tools = len(entry.tool_calls)
        patch = "✓" if entry.applied_patch else ""
        
        lines.append(f"{i}. {timestamp} | {task} | {model} | {tokens}t | {tools} tools {patch}")
    
    lines.append("")
    lines.append("Commands: Enter to view details, Y to copy response, R to re-run")
    return "\n".join(lines)

# LSP commands
def lsp_restart(language: str = "python") -> str:
    """Restart LSP server for a language."""
    from editor.diagnostics import LSPDiagnosticsManager
    # This is a global instance, need to access it somehow
    # For now, placeholder
    return f"LSP server for {language} restarted"

def lsp_toggle() -> str:
    """Toggle LSP diagnostics overlay."""
    from editor.diagnostics import LSPDiagnosticsManager
    # Placeholder
    return "LSP diagnostics toggled"

def lsp_hover() -> str:
    """Show hover information at cursor."""
    from editor.lsp_actions import lsp_handler
    # Placeholder - will be implemented with cursor position
    return "Hover: Not implemented yet"

def lsp_definition() -> str:
    """Go to definition."""
    from editor.lsp_actions import lsp_handler
    # Placeholder
    return "Definition: Not implemented yet"

def lsp_references() -> str:
    """Find references."""
    from editor.lsp_actions import lsp_handler
    # Placeholder
    return "References: Not implemented yet"

def lsp_rename(new_name: str) -> str:
    """Rename symbol."""
    from editor.lsp_actions import lsp_handler
    # Placeholder
    return f"Rename to {new_name}: Not implemented yet"

def lsp_format() -> str:
    """Format current document."""
    from editor.lsp_actions import lsp_handler
    # This needs to be called from the editor context with current file
    # For now, placeholder
    return "Format: Use Ctrl+Shift+F in editor"

def lsp_organize_imports() -> str:
    """Organize imports in current file."""
    from editor.lsp_actions import lsp_handler
    # This needs to be called from the editor context with current file
    # For now, placeholder
    return "Organize imports: Use Alt-O in editor"

# Plan commands
def ai_plan_apply(plan_id: str, step_indices: Optional[str] = None) -> str:
    """Apply a plan with optional step selection."""
    from ai.plan_executor import PlanExecutor
    from ai.planner import AIPlanner
    
    planner = AIPlanner()
    plan = planner.load_plan(plan_id)
    if not plan:
        return f"Plan {plan_id} not found"
    
    executor = PlanExecutor()
    
    # Parse step indices
    selected_steps = None
    if step_indices:
        try:
            selected_steps = [int(x.strip()) for x in step_indices.split(",")]
        except ValueError:
            return "Invalid step indices format"
    
    success, message = executor.apply_plan(plan, selected_steps)
    return message

def ai_plan_rollback(plan_id: str) -> str:
    """Rollback an applied plan."""
    from ai.plan_executor import PlanExecutor
    
    executor = PlanExecutor()
    success, message = executor.rollback_plan(plan_id)
    return message

def ai_plan_cleanup(plan_id: str) -> str:
    """Clean up plan artifacts."""
    from ai.plan_executor import PlanExecutor
    
    executor = PlanExecutor()
    success, message = executor.cleanup_plan(plan_id)
    return message

def ai_plan_playground(plan_id: str, step_indices: Optional[str] = None) -> str:
    """Apply a plan in playground worktree with optional step selection."""
    from ai.plan_executor import PlanExecutor
    from ai.planner import AIPlanner
    
    planner = AIPlanner()
    plan = planner.load_plan(plan_id)
    if not plan:
        return f"Plan {plan_id} not found"
    
    executor = PlanExecutor()
    
    # Parse step indices
    selected_steps = None
    if step_indices:
        try:
            selected_steps = [int(x.strip()) for x in step_indices.split(",")]
        except ValueError:
            return "Invalid step indices format"
    
    success, message, playground_info = executor.apply_plan_playground(plan, selected_steps)
    if success and playground_info:
        return f"{message}\nPlayground Summary:\n- Worktree: {playground_info.worktree_path}\n- Branch: {playground_info.branch_name}\n- Files: {playground_info.total_files}\n- Commits: {len(playground_info.commits)}\n- Test Results: {playground_info.test_results or 'N/A'}"
    return message

def ai_plan_promote(plan_id: str, mode: str = "apply_patches") -> str:
    """Promote a playground plan."""
    from ai.plan_executor import PlanExecutor
    
    executor = PlanExecutor()
    success, message = executor.promote_playground(plan_id, mode)
    return message

def ai_plan_cleanup_playground(plan_id: str) -> str:
    """Clean up a playground worktree."""
    from ai.plan_executor import PlanExecutor
    
    executor = PlanExecutor()
    success, message = executor.cleanup_playground(plan_id)
    return message

# Git blame
def git_blame() -> str:
    """Show git blame for current line."""
    # This would need cursor position from editor
    # Placeholder
    return "Blame: Not implemented yet"

# Git stash commands
def git_stash_save(message: str) -> str:
    """Save current changes to stash."""
    try:
        cmd = ["git", "stash", "push", "-u", "-m", message]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        if result.returncode == 0:
            return "Changes stashed successfully"
        else:
            return f"Git stash failed: {result.stderr}"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "Git not available"

def git_stash_list() -> str:
    """List all stashes."""
    try:
        result = subprocess.run(
            ["git", "stash", "list"],
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        if result.returncode == 0:
            stashes = result.stdout.strip()
            if not stashes:
                return "No stashes"
            return stashes
        else:
            return f"Git stash list failed: {result.stderr}"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "Git not available"

def git_stash_pop(index: Optional[int] = None) -> str:
    """Pop a stash (default latest)."""
    try:
        cmd = ["git", "stash", "pop"]
        if index is not None:
            cmd.append(f"stash@{{{index}}}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        if result.returncode == 0:
            return "Stash popped successfully"
        else:
            return f"Git stash pop failed: {result.stderr}"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "Git not available"

def git_stash_apply(index: Optional[int] = None) -> str:
    """Apply a stash without removing it."""
    try:
        cmd = ["git", "stash", "apply"]
        if index is not None:
            cmd.append(f"stash@{{{index}}}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        if result.returncode == 0:
            return "Stash applied successfully"
        else:
            return f"Git stash apply failed: {result.stderr}"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "Git not available"

def git_stash_drop(index: Optional[int] = None) -> str:
    """Drop a stash."""
    try:
        cmd = ["git", "stash", "drop"]
        if index is not None:
            cmd.append(f"stash@{{{index}}}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        if result.returncode == 0:
            return "Stash dropped successfully"
        else:
            return f"Git stash drop failed: {result.stderr}"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "Git not available"

# Git branch switcher
def git_branch_switcher() -> str:
    """Show branch switcher modal."""
    # This would show a modal with branches
    # Placeholder
    return "Branch switcher: Not implemented yet"

# Index commands
def index_rebuild() -> str:
    """Rebuild all indexes (symbols + embeddings + graph)."""
    from pathlib import Path
    from indexer import build_or_load_symbols, build_or_load_embeddings, build_or_load_graph
    
    project_root = Path.cwd()
    
    try:
        # Rebuild symbols
        symbols = build_or_load_symbols(project_root)
        
        # Rebuild embeddings
        embeddings = build_or_load_embeddings(project_root, force=True)
        
        # Rebuild graph
        graph = build_or_load_graph(project_root, force=True)
        
        return f"Indexes rebuilt successfully:\n- Symbols: {len(symbols.symbols)} symbols\n- Embeddings: {len(embeddings.vectors) if embeddings.vectors is not None else 0} chunks\n- Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges"
    except Exception as e:
        return f"Index rebuild failed: {e}"

def index_rebuild_emb() -> str:
    """Rebuild embeddings index only."""
    from pathlib import Path
    from indexer import build_or_load_embeddings
    
    project_root = Path.cwd()
    
    try:
        embeddings = build_or_load_embeddings(project_root, force=True)
        chunk_count = len(embeddings.vectors) if embeddings.vectors is not None else 0
        return f"Embeddings index rebuilt: {chunk_count} chunks"
    except Exception as e:
        return f"Embeddings rebuild failed: {e}"

def index_stats() -> str:
    """Show index statistics."""
    from pathlib import Path
    from indexer import build_or_load_symbols, build_or_load_embeddings, build_or_load_graph
    import time
    
    project_root = Path.cwd()
    
    try:
        symbols = build_or_load_symbols(project_root)
        embeddings = build_or_load_embeddings(project_root)
        graph = build_or_load_graph(project_root)
        
        lines = ["Index Statistics:"]
        
        # Symbols
        lines.append(f"- Symbols: {len(symbols.symbols)} symbols")
        
        # Embeddings
        if embeddings.vectors is not None:
            chunk_count = len(embeddings.vectors)
            backend = "SentenceTransformers"
            if embeddings.model.startswith("sklearn"):
                backend = "TF-IDF"
            elif embeddings.model == "hash":
                backend = "Hashed BoW"
            
            lines.append(f"- Embeddings: {chunk_count} chunks, {embeddings.dim}D, backend: {backend}")
            lines.append(f"  Model: {embeddings.model}")
        else:
            lines.append("- Embeddings: disabled")
        
        # Graph
        lines.append(f"- Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        
        # Build times
        if embeddings.built_at:
            lines.append(f"- Last embeddings build: {time.ctime(embeddings.built_at)}")
        if graph.built_at:
            lines.append(f"- Last graph build: {time.ctime(graph.built_at)}")
        
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to get index stats: {e}"

def index_pause() -> str:
    """Pause the file system watcher."""
    from indexer.watch import stop_watching
    stop_watching()
    return "Index watcher paused"

def index_resume() -> str:
    """Resume the file system watcher."""
    from pathlib import Path
    from indexer.watch import start_watching
    project_root = Path.cwd()
    start_watching(project_root)
    return "Index watcher resumed"

# Pipeline commands
def ai_spec(description: str) -> str:
    """Generate a specification from description."""
    from editor.pipelineview import show_pipeline_view
    result = show_pipeline_view(description)
    if result and result.get("spec"):
        return f"Specification generated: {result['spec']['title']}"
    return "Specification generation cancelled"

def ai_gen_tests(description: str) -> str:
    """Generate tests from description (runs full pipeline)."""
    from editor.pipelineview import show_pipeline_view
    result = show_pipeline_view(description)
    if result and result.get("tests"):
        test_files = len(result['tests']['files'])
        return f"Test suite generated: {test_files} test files"
    return "Test generation cancelled"

def ai_implement(description: str) -> str:
    """Generate implementation from description (runs full pipeline)."""
    from editor.pipelineview import show_pipeline_view
    result = show_pipeline_view(description)
    if result and result.get("implementation"):
        impl_files = len(result['implementation']['files'])
        return f"Implementation generated: {impl_files} files modified"
    return "Implementation generation cancelled"

def ai_pipeline(description: str) -> str:
    """Run the complete spec→tests→code pipeline."""
    from editor.pipelineview import show_pipeline_view
    result = show_pipeline_view(description)
    if result:
        spec_title = result['spec']['title'] if result.get('spec') else 'N/A'
        test_files = len(result['tests']['files']) if result.get('tests') else 0
        impl_files = len(result['implementation']['files']) if result.get('implementation') else 0
        return f"Pipeline completed:\n- Spec: {spec_title}\n- Tests: {test_files} files\n- Code: {impl_files} files"
    return "Pipeline cancelled"

def budget_status() -> str:
    """Show current budget status."""
    from core.billing import billing_manager
    info = billing_manager.check_budget()
    return f"Monthly budget: ${info['monthly_cost']:.2f} / ${info['budget']:.2f}\nStatus: {info['status']}\n{info['message'] or ''}"

def budget_set(amount: float) -> str:
    """Set monthly budget."""
    from core.config import get_config
    # Note: This would need to update config file, for now just show
    return f"Budget set to ${amount:.2f} (restart required to take effect)"

def budget_reset() -> str:
    """Reset budget for current month."""
    from core.billing import billing_manager
    billing_manager.reset_budget()
    return "Budget reset for current month"

def budget_export(path: str = "billing.csv") -> str:
    """Export budget history to CSV."""
    from core.billing import billing_manager
    billing_manager.export_csv(path)
    return f"Budget exported to {path}"

# Plugin management commands
def plugin_list() -> str:
    """List all loaded plugins."""
    from plugins import plugin_manager
    plugins = plugin_manager.list_plugins()
    if not plugins:
        return "No plugins loaded"

    lines = ["Loaded Plugins:"]
    for plugin in plugins:
        status = "enabled" if plugin.enabled else "disabled"
        safe = "safe" if plugin.safe_mode else "unsafe"
        lines.append(f"- {plugin.name} v{plugin.version} ({status}, {safe}): {plugin.description}")
    return "\n".join(lines)

def plugin_load(name: str) -> str:
    """Load a plugin."""
    from plugins import plugin_manager
    if plugin_manager.load_plugin(name):
        return f"Plugin {name} loaded successfully"
    return f"Failed to load plugin {name}"

def plugin_unload(name: str) -> str:
    """Unload a plugin."""
    from plugins import plugin_manager
    if plugin_manager.unload_plugin(name):
        return f"Plugin {name} unloaded successfully"
    return f"Failed to unload plugin {name}"

def plugin_enable(name: str) -> str:
    """Enable a plugin."""
    from plugins import plugin_manager
    if plugin_manager.enable_plugin(name):
        return f"Plugin {name} enabled"
    return f"Failed to enable plugin {name}"

def plugin_disable(name: str) -> str:
    """Disable a plugin."""
    from plugins import plugin_manager
    if plugin_manager.disable_plugin(name):
        return f"Plugin {name} disabled"
    return f"Failed to disable plugin {name}"

def plugin_discover() -> str:
    """Discover available plugins."""
    from plugins import plugin_manager
    plugins = plugin_manager.discover_plugins()
    if not plugins:
        return "No plugins discovered"

    lines = ["Discovered Plugins:"]
    lines.extend(f"- {name}" for name in plugins)
    return "\n".join(lines)

def plugin_validate(name: str) -> str:
    """Validate a plugin for security."""
    from plugins import plugin_manager
    validation = plugin_manager.validate_plugin(name)
    if validation["safe"]:
        return f"Plugin {name} is safe to use"
    else:
        lines = [f"Plugin {name} validation issues:"]
        lines.extend(f"- {error}" for error in validation["errors"])
        lines.extend(f"- Warning: {warning}" for warning in validation["warnings"])
        return "\n".join(lines)

def codemod() -> str:
    """Open codemod modal for bulk transformations."""
    from editor.ws_codemod import ws_codemod_runner
    ws_codemod_runner.run_codemod_workflow()
    return "Codemod workflow started"
def ws_refactor_format() -> str:
    """Format all Python files in workspace."""
    import asyncio
    from editor.workspace_refactor import workspace_refactor

    async def run_format():
        plan = await workspace_refactor.plan_format()
        if not plan:
            return "No files to format"

        success = await workspace_refactor.apply_plan(plan)
        return f"Format {'completed' if success else 'failed'}: {plan.summary()}"

    try:
        return asyncio.run(run_format())
    except Exception as e:
        return f"Format failed: {e}"

def ws_refactor_organize_imports() -> str:
    """Organize imports in all Python files."""
    import asyncio
    from editor.workspace_refactor import workspace_refactor

    async def run_organize():
        plan = await workspace_refactor.plan_organize_imports()
        if not plan:
            return "No files to organize"

        success = await workspace_refactor.apply_plan(plan)
        return f"Organize imports {'completed' if success else 'failed'}: {plan.summary()}"

    try:
        return asyncio.run(run_organize())
    except Exception as e:
        return f"Organize imports failed: {e}"

def ws_refactor_rename(file_path: str, line: int, character: int, new_name: str) -> str:
    """Rename symbol at position."""
    import asyncio
    from editor.workspace_refactor import workspace_refactor

    async def run_rename():
        plan = await workspace_refactor.plan_rename(file_path, line, character, new_name)
        if not plan:
            return "No rename targets found"

        success = await workspace_refactor.apply_plan(plan)
        return f"Rename {'completed' if success else 'failed'}: {plan.summary()}"

    try:
        return asyncio.run(run_rename())
    except Exception as e:
        return f"Rename failed: {e}"

# Register commands
registry.register("ai-explain", ai_explain)
registry.register("ai-refactor", ai_refactor)
registry.register("ai-fix", ai_fix_error)
registry.register("ai-tests", ai_add_tests)
registry.register("ai-fix-tests", ai_fix_tests)
registry.register("git-status", git_status)
registry.register("git-diff", git_diff)
registry.register("git-stage", git_stage)
registry.register("git-unstage", git_unstage)
registry.register("git-commit", git_commit)
registry.register("ai-history", ai_history)
registry.register("lsp-restart", lsp_restart)
registry.register("lsp-toggle", lsp_toggle)
registry.register("lsp-hover", lsp_hover)
registry.register("lsp-definition", lsp_definition)
registry.register("lsp-references", lsp_references)
registry.register("lsp-rename", lsp_rename)
registry.register("lsp-format", lsp_format)
registry.register("lsp-organize-imports", lsp_organize_imports)
registry.register("ai-plan-apply", ai_plan_apply)
registry.register("ai-plan-rollback", ai_plan_rollback)
registry.register("ai-plan-cleanup", ai_plan_cleanup)
registry.register("ai-plan-playground", ai_plan_playground)
registry.register("ai-plan-promote", ai_plan_promote)
registry.register("ai-plan-cleanup-playground", ai_plan_cleanup_playground)
registry.register("git-blame", git_blame)
registry.register("git-stash-save", git_stash_save)
registry.register("git-stash-list", git_stash_list)
registry.register("git-stash-pop", git_stash_pop)
registry.register("git-stash-apply", git_stash_apply)
registry.register("git-stash-drop", git_stash_drop)
registry.register("git-branch-switcher", git_branch_switcher)
registry.register("index-rebuild", index_rebuild)
registry.register("index-rebuild-emb", index_rebuild_emb)
registry.register("index-stats", index_stats)
registry.register("index-pause", index_pause)
registry.register("index-resume", index_resume)
registry.register("ai-spec", ai_spec)
registry.register("ai-gen-tests", ai_gen_tests)
registry.register("ai-implement", ai_implement)
registry.register("ai-pipeline", ai_pipeline)
registry.register("budget", budget_status)
registry.register("budget-set", budget_set)
registry.register("budget-reset", budget_reset)
registry.register("budget-export", budget_export)
registry.register("plugin-list", plugin_list)
registry.register("plugin-load", plugin_load)
registry.register("plugin-unload", plugin_unload)
registry.register("plugin-enable", plugin_enable)
registry.register("plugin-disable", plugin_disable)
registry.register("plugin-discover", plugin_discover)
registry.register("plugin-validate", plugin_validate)
registry.register("ws-refactor-format", ws_refactor_format)
registry.register("ws-refactor-organize-imports", ws_refactor_organize_imports)
registry.register("ws-refactor-rename", ws_refactor_rename)
registry.register("codemod", codemod)