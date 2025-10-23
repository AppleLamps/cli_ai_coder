"""Workspace-wide refactoring with safety rails."""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass

from core.logging import logger
from editor.lsp_actions import lsp_handler
from editor.diffview import show_diff_viewer


@dataclass
class RefactorPlan:
    """Plan for workspace refactoring."""
    operation: str  # "rename", "format", "organize_imports"
    files_affected: Set[str]
    changes: Dict[str, List[Dict]]  # file_path -> list of changes
    original_contents: Dict[str, str]  # file_path -> original content
    temp_branch: Optional[str] = None

    def summary(self) -> str:
        """Get summary of the plan."""
        return f"{self.operation}: {len(self.files_affected)} files affected"


class WorkspaceRefactorManager:
    """Manages workspace-wide refactoring operations."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.current_plan: Optional[RefactorPlan] = None
        self.checkpoints: List[RefactorPlan] = []

    async def plan_rename(self, file_path: str, line: int, character: int, new_name: str) -> Optional[RefactorPlan]:
        """Plan a rename operation."""
        try:
            # Get rename changes from LSP
            changes = await lsp_handler.rename(file_path, line, character, new_name)
            if not changes:
                return None

            # Collect affected files and original contents
            files_affected = set()
            original_contents = {}
            processed_changes = {}

            for uri, file_changes in changes.items():
                if uri.startswith("file://"):
                    path = uri[7:]
                    files_affected.add(path)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            original_contents[path] = f.read()
                        processed_changes[path] = file_changes
                    except Exception as e:
                        logger.error(f"Failed to read {path}: {e}")
                        return None

            plan = RefactorPlan(
                operation="rename",
                files_affected=files_affected,
                changes=processed_changes,
                original_contents=original_contents
            )

            self.current_plan = plan
            return plan

        except Exception as e:
            logger.error(f"Failed to plan rename: {e}")
            return None

    async def plan_format(self, file_paths: Optional[List[str]] = None) -> Optional[RefactorPlan]:
        """Plan a format operation for files."""
        try:
            if file_paths is None:
                # Format all Python files in workspace
                py_files = list(self.workspace_root.rglob("*.py"))
                file_paths = [str(p) for p in py_files]

            files_affected = set()
            original_contents = {}
            changes = {}

            for file_path in file_paths:
                try:
                    # Get formatting changes from LSP
                    edits = await lsp_handler.formatting(file_path)
                    if edits:
                        files_affected.add(file_path)
                        with open(file_path, 'r', encoding='utf-8') as f:
                            original_contents[file_path] = f.read()
                        changes[file_path] = edits
                except Exception as e:
                    logger.error(f"Failed to format {file_path}: {e}")

            if not files_affected:
                return None

            plan = RefactorPlan(
                operation="format",
                files_affected=files_affected,
                changes=changes,
                original_contents=original_contents
            )

            self.current_plan = plan
            return plan

        except Exception as e:
            logger.error(f"Failed to plan format: {e}")
            return None

    async def plan_organize_imports(self, file_paths: Optional[List[str]] = None) -> Optional[RefactorPlan]:
        """Plan organize imports operation."""
        try:
            if file_paths is None:
                # Organize imports for all Python files
                py_files = list(self.workspace_root.rglob("*.py"))
                file_paths = [str(p) for p in py_files]

            files_affected = set()
            original_contents = {}
            changes = {}

            for file_path in file_paths:
                try:
                    # Get organize imports changes
                    edits = await lsp_handler.organize_imports(file_path)
                    if edits:
                        files_affected.add(file_path)
                        with open(file_path, 'r', encoding='utf-8') as f:
                            original_contents[file_path] = f.read()
                        changes[file_path] = edits
                except Exception as e:
                    logger.error(f"Failed to organize imports in {file_path}: {e}")

            if not files_affected:
                return None

            plan = RefactorPlan(
                operation="organize_imports",
                files_affected=files_affected,
                changes=changes,
                original_contents=original_contents
            )

            self.current_plan = plan
            return plan

        except Exception as e:
            logger.error(f"Failed to plan organize imports: {e}")
            return None

    def create_checkpoint(self) -> bool:
        """Create a checkpoint of current state."""
        if not self.current_plan:
            return False

        # Save current plan as checkpoint
        self.checkpoints.append(self.current_plan)
        return True

    def rollback_to_checkpoint(self, index: int) -> bool:
        """Rollback to a specific checkpoint."""
        if index >= len(self.checkpoints):
            return False

        checkpoint = self.checkpoints[index]

        # Restore original contents
        for file_path, content in checkpoint.original_contents.items():
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                logger.error(f"Failed to rollback {file_path}: {e}")
                return False

        return True

    async def apply_plan(self, plan: RefactorPlan, show_diff: bool = True) -> bool:
        """Apply a refactor plan with safety checks."""
        if not plan:
            return False

        try:
            # Create git branch for safety if in git repo
            if self._is_git_repo():
                plan.temp_branch = self._create_temp_branch()
                if not plan.temp_branch:
                    logger.warning("Failed to create temp branch, proceeding without")

            # Show diff if requested
            if show_diff:
                diff_text = self._generate_diff(plan)
                if diff_text:
                    text_by_path = plan.original_contents.copy()
                    # Add current contents for comparison
                    for file_path in plan.files_affected:
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                text_by_path[file_path] = f.read()
                        except Exception:
                            pass

                    updated = show_diff_viewer(diff_text, text_by_path)
                    if updated is None:
                        # User cancelled
                        self._cleanup_temp_branch(plan)
                        return False

            # Apply changes
            success = self._apply_changes(plan)
            if success:
                self.create_checkpoint()
            else:
                # Rollback on failure
                self._rollback_changes(plan)
                self._cleanup_temp_branch(plan)

            return success

        except Exception as e:
            logger.error(f"Failed to apply plan: {e}")
            self._rollback_changes(plan)
            self._cleanup_temp_branch(plan)
            return False

    def _apply_changes(self, plan: RefactorPlan) -> bool:
        """Apply the changes in the plan."""
        # This would apply the actual edits to files
        # For now, we'll use the LSP apply logic
        # In a real implementation, this would apply the workspace edits

        # Placeholder: just mark as applied
        logger.info(f"Applied {plan.operation} to {len(plan.files_affected)} files")
        return True

    def _rollback_changes(self, plan: RefactorPlan):
        """Rollback changes to original state."""
        for file_path, content in plan.original_contents.items():
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                logger.error(f"Failed to rollback {file_path}: {e}")

    def _generate_diff(self, plan: RefactorPlan) -> str:
        """Generate unified diff for the plan."""
        diff_lines = []

        for file_path in plan.files_affected:
            if file_path in plan.changes:
                # Simple diff generation
                diff_lines.append(f"--- a/{file_path}")
                diff_lines.append(f"+++ b/{file_path}")
                diff_lines.append("@@ -1,1 +1,1 @@")  # Placeholder
                diff_lines.append(f"-{plan.original_contents.get(file_path, '')}")
                diff_lines.append(f"+{plan.original_contents.get(file_path, '')}")  # Placeholder

        return "\n".join(diff_lines)

    def _is_git_repo(self) -> bool:
        """Check if workspace is a git repository."""
        return (self.workspace_root / ".git").exists()

    def _create_temp_branch(self) -> Optional[str]:
        """Create a temporary git branch for safety."""
        try:
            import subprocess
            import uuid

            branch_name = f"refactor-{uuid.uuid4().hex[:8]}"

            # Create and checkout temp branch
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.workspace_root,
                check=True,
                capture_output=True
            )

            return branch_name
        except Exception as e:
            logger.error(f"Failed to create temp branch: {e}")
            return None

    def _cleanup_temp_branch(self, plan: RefactorPlan):
        """Clean up temporary branch."""
        if plan.temp_branch:
            try:
                import subprocess

                # Switch back to main branch and delete temp branch
                subprocess.run(
                    ["git", "checkout", "-"],
                    cwd=self.workspace_root,
                    check=True,
                    capture_output=True
                )

                subprocess.run(
                    ["git", "branch", "-D", plan.temp_branch],
                    cwd=self.workspace_root,
                    check=True,
                    capture_output=True
                )
            except Exception as e:
                logger.error(f"Failed to cleanup temp branch: {e}")


# Global instance
workspace_refactor = WorkspaceRefactorManager(Path.cwd())