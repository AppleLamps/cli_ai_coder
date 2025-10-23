"""Workspace codemod runner with preview and bulk application."""

import asyncio
import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from prompt_toolkit.widgets import Button, Dialog, Label, RadioList, TextArea, CheckboxList
from prompt_toolkit.layout import HSplit, VSplit

from .diffview import show_diff_viewer
from ..ai.plan_executor import PlanExecutor
from ..core.config import get_config
from ..core.logging import logger


@dataclass
class CodemodTarget:
    """Target file for codemod application."""
    path: str
    diff: str
    selected_hunks: List[int]


class WorkspaceCodemodRunner:
    """Runner for applying codemods across workspace files."""

    def __init__(self):
        self.config = get_config()
        self.available_mods = self._load_available_mods()

    def _load_available_mods(self) -> Dict[str, Any]:
        """Load available codemod classes."""
        mods = {}

        # Python mods
        try:
            from ..codemods.python_libcst import (
                RenameSymbolCodemod,
                ConvertPrintToLoggingCodemod,
                AddTypeHintsCodemod
            )
            mods.update({
                'rename_symbol': RenameSymbolCodemod,
                'convert_print_to_logging': ConvertPrintToLoggingCodemod,
                'add_type_hints': AddTypeHintsCodemod,
            })
        except ImportError:
            logger.warning("LibCST not available, Python codemods disabled")

        # JS/TS mods
        try:
            from ..codemods.js_ts import (
                RenameExportCodemod,
                RemoveConsoleCodemod,
                OrganizeImportsBestEffortCodemod
            )
            mods.update({
                'rename_export': RenameExportCodemod,
                'remove_console': RemoveConsoleCodemod,
                'organize_imports_best_effort': OrganizeImportsBestEffortCodemod,
            })
        except ImportError:
            logger.warning("JS/TS codemods not available")

        return mods

    def show_codemod_modal(self) -> Optional[Dict[str, Any]]:
        """Show modal for selecting codemod and parameters."""
        # This would be implemented with prompt_toolkit widgets
        # For now, return a placeholder configuration
        return {
            'mod_name': 'rename_symbol',
            'params': {'old_name': 'old_func', 'new_name': 'new_func'},
            'scope': 'current_file',  # current_file, changed_files, glob
            'glob_pattern': '*.py'
        }

    def get_target_files(self, scope: str, glob_pattern: str = "*.py") -> List[str]:
        """Get list of target files based on scope."""
        config = get_config()
        workspace_root = Path.cwd()

        if scope == "current_file":
            # This would need to be passed from the editor
            return ["current_file.py"]  # placeholder
        elif scope == "changed_files":
            # Get git changed files
            import subprocess
            try:
                result = subprocess.run(
                    ["git", "diff", "--name-only"],
                    capture_output=True,
                    text=True,
                    cwd=workspace_root
                )
                if result.returncode == 0:
                    files = result.stdout.strip().splitlines()
                    return [f for f in files if fnmatch.fnmatch(f, glob_pattern)]
            except (subprocess.SubprocessError, FileNotFoundError):
                pass
        elif scope == "glob":
            # Find files matching glob pattern
            all_files = []
            for pattern in glob_pattern.split():
                all_files.extend(workspace_root.glob(pattern))
            return [str(f.relative_to(workspace_root)) for f in all_files if f.is_file()]

        return []

    def generate_diffs(self, mod_name: str, params: Dict[str, Any], files: List[str]) -> List[CodemodTarget]:
        """Generate diffs for all target files."""
        if mod_name not in self.available_mods:
            return []

        mod_class = self.available_mods[mod_name]
        mod_instance = mod_class(**params)

        targets = []
        workspace_root = Path.cwd()

        for file_path in files:
            full_path = workspace_root / file_path
            if not full_path.exists():
                continue

            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                diff = mod_instance.preview(str(file_path), content)
                if diff.strip():  # Only include files with changes
                    targets.append(CodemodTarget(
                        path=file_path,
                        diff=diff,
                        selected_hunks=[]
                    ))
            except (IOError, UnicodeDecodeError) as e:
                logger.warning(f"Could not read {file_path}: {e}")
                continue

        return targets

    def apply_codemods(self, targets: List[CodemodTarget], mod_name: str, params: Dict[str, Any]) -> bool:
        """Apply selected codemods via Plan Executor."""
        if not targets:
            return False

        # Check limits
        total_files = len(targets)
        if total_files > self.config.codemods_max_files:
            logger.warning(f"Too many files ({total_files} > {self.config.codemods_max_files})")
            return False

        # Estimate total changed lines (rough estimate)
        total_changed_lines = sum(len(target.diff.splitlines()) for target in targets)
        if total_changed_lines > self.config.codemods_max_total_changed_lines:
            logger.warning(f"Too many changed lines ({total_changed_lines} > {self.config.codemods_max_total_changed_lines})")
            return False

        # Import Plan and PlanStep
        from ..ai.planner import Plan, PlanStep
        import time

        # Create plan steps from targets
        steps = []
        for target in targets:
            steps.append(PlanStep(
                file=target.path,
                intent="modify",
                explanation=f"Apply {mod_name} codemod",
                constraints={"diff": target.diff}
            ))

        # Create plan
        plan = Plan(
            title=f"Codemod: {mod_name}",
            rationale=f"Apply {mod_name} codemod to {len(targets)} files",
            steps=steps,
            created_at=time.time(),
            plan_id=f"codemod_{mod_name}_{int(time.time())}"
        )

        # Use PlanExecutor to apply
        executor = PlanExecutor()
        success, message = executor.apply_plan(plan)
        return success

    def run_codemod_workflow(self):
        """Run the complete codemod workflow."""
        # Step 1: Show modal to select mod and scope
        config = self.show_codemod_modal()
        if not config:
            return

        # Step 2: Get target files
        files = self.get_target_files(config['scope'], config.get('glob_pattern', '*.py'))
        if not files:
            logger.info("No target files found")
            return

        # Step 3: Generate diffs
        targets = self.generate_diffs(config['mod_name'], config['params'], files)
        if not targets:
            logger.info("No changes to apply")
            return

        # Step 4: Show Plan Viewer with diffs
        # This would integrate with the existing Plan Viewer
        # For now, just apply directly
        success = self.apply_codemods(targets, config['mod_name'], config['params'])
        if success:
            logger.info(f"Codemod {config['mod_name']} applied successfully")
        else:
            logger.error(f"Failed to apply codemod {config['mod_name']}")


# Global instance
ws_codemod_runner = WorkspaceCodemodRunner()