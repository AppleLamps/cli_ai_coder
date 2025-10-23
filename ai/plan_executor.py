"""Plan execution engine for safe multi-file changes with Git integration."""

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from graphlib import TopologicalSorter

from ai.patches import apply_unified_diff
from ai.planner import AIPlanner, Plan, PlanStep
from ai.history import history
from core.config import get_config


@dataclass
class PlaygroundInfo:
    """Information about a playground worktree."""
    plan_id: str
    worktree_path: Path
    branch_name: str
    original_head: str
    created_at: float
    commits: List[str]
    total_files: int
    total_changed_lines: int
    test_results: Optional[str] = None


@dataclass
class AppliedPlanInfo:
    """Information about an applied plan."""
    plan_id: str
    branch_name: str
    original_branch: str
    original_head: str
    commits: List[str]  # List of commit SHAs
    applied_at: float
    total_files: int
    total_changed_lines: int
    autostash_id: Optional[str] = None


class PlanExecutor:
    """Executes plans with Git safety and rollback capabilities."""

    def __init__(self):
        self.config = get_config()
        self.planner = AIPlanner()
        self.plans_dir = self.planner.plans_dir
        self.applied_dir = self.plans_dir / "applied"

    def apply_plan(self, plan: Plan, selected_steps: Optional[List[int]] = None) -> Tuple[bool, str]:
        """
        Apply a plan with Git safety.

        Args:
            plan: The plan to apply.
            selected_steps: Indices of steps to apply (None for all).

        Returns:
            (success, message)
        """
        try:
            # Preflight checks
            preflight_result = self._preflight(plan, selected_steps)
            if not preflight_result[0]:
                return False, preflight_result[1] or "Preflight failed"

            branch_name, original_branch, original_head, autostash_id = preflight_result[2]

            # Branching
            if not self._create_branch(branch_name):
                return False, f"Failed to create branch {branch_name}"

            # Apply steps
            commits, applied_steps = self._apply_steps(plan, selected_steps or list(range(len(plan.steps))))

            # Finalize
            applied_info = AppliedPlanInfo(
                plan_id=plan.plan_id,
                branch_name=branch_name,
                original_branch=original_branch,
                original_head=original_head,
                commits=commits,
                applied_at=time.time(),
                total_files=len(set(step.file for step in applied_steps)),
                total_changed_lines=sum(self._estimate_changed_lines(step) for step in applied_steps),
                autostash_id=autostash_id
            )

            self._finalize(applied_info)

            return True, f"Plan {plan.plan_id} applied successfully on branch {branch_name} with {len(commits)} commits"

        except Exception as e:
            return False, f"Plan application failed: {e}"

    def rollback_plan(self, plan_id: str) -> Tuple[bool, str]:
        """
        Rollback an applied plan.

        Args:
            plan_id: ID of the plan to rollback.

        Returns:
            (success, message)
        """
        applied_info = self._load_applied_info(plan_id)
        if not applied_info:
            return False, f"No applied info found for plan {plan_id}"

        try:
            # Checkout original branch
            if not self._run_git(["checkout", applied_info.original_branch]):
                return False, "Failed to checkout original branch"

            # Hard reset to original HEAD
            if not self._run_git(["reset", "--hard", applied_info.original_head]):
                return False, "Failed to reset to original HEAD"

            # Pop autostash if present
            if applied_info.autostash_id:
                self._run_git(["stash", "pop", applied_info.autostash_id])

            # Delete temp branch
            if not self.config.planner_keep_branch_on_rollback:
                self._run_git(["branch", "-D", applied_info.branch_name])

            # Remove applied info
            applied_file = self.applied_dir / f"{plan_id}.json"
            if applied_file.exists():
                applied_file.unlink()

            return True, f"Plan {plan_id} rolled back successfully"

        except Exception as e:
            return False, f"Rollback failed: {e}"

    def cleanup_plan(self, plan_id: str) -> Tuple[bool, str]:
        """
        Clean up an applied plan (delete branch, remove stashes).

        Args:
            plan_id: ID of the plan to cleanup.

        Returns:
            (success, message)
        """
        applied_info = self._load_applied_info(plan_id)
        if not applied_info:
            return False, f"No applied info found for plan {plan_id}"

        try:
            # Delete branch if it exists
            branches_output = self._run_git_output(["branch", "--list", applied_info.branch_name])
            if branches_output and applied_info.branch_name in branches_output:
                self._run_git(["branch", "-D", applied_info.branch_name])

            # Remove autostash if still present
            if applied_info.autostash_id:
                stashes_output = self._run_git_output(["stash", "list"])
                if stashes_output and applied_info.autostash_id in stashes_output:
                    # Find stash index
                    lines = stashes_output.splitlines()
                    for i, line in enumerate(lines):
                        if applied_info.autostash_id in line:
                            self._run_git(["stash", "drop", f"stash@{{{i}}}"])
                            break

            return True, f"Plan {plan_id} cleaned up successfully"

        except Exception as e:
            return False, f"Cleanup failed: {e}"

    def _preflight(self, plan: Plan, selected_steps: Optional[List[int]]) -> Tuple[bool, Optional[str], Optional[Tuple[str, str, str, Optional[str]]]]:
        """Run preflight checks."""
        # Detect repo root
        if not self._is_git_repo():
            return False, "Not a git repository", None

        # Get current branch and HEAD
        original_branch = self._get_current_branch()
        original_head = self._get_current_commit()
        if not original_branch or not original_head:
            return False, "Cannot determine current branch or HEAD", None

        # Check working tree status
        is_dirty = self._is_working_tree_dirty()
        autostash_id = None

        if is_dirty:
            if self.config.planner_autostash:
                # Create autostash
                timestamp = int(time.time())
                stash_msg = f"cli_ai_coder autostash {timestamp}"
                if self._run_git(["stash", "push", "-u", "-m", stash_msg]):
                    # Get stash ID
                    stashes_output = self._run_git_output(["stash", "list"])
                    if stashes_output:
                        autostash_id = stashes_output.splitlines()[0].split(":")[0].strip()
                else:
                    return False, "Failed to create autostash", None
            else:
                return False, "Working tree is dirty and autostash is disabled", None

        # Validate plan
        steps_to_apply = [plan.steps[i] for i in (selected_steps or range(len(plan.steps)))]
        if not self._validate_plan(plan, steps_to_apply):
            return False, "Plan validation failed", None

        # Estimate changes
        total_changed_lines = sum(self._estimate_changed_lines(step) for step in steps_to_apply)
        if total_changed_lines > self.config.planner_max_total_changed_lines:
            return False, f"Estimated changes ({total_changed_lines} lines) exceed limit ({self.config.planner_max_total_changed_lines})", None

        # Generate branch name
        timestamp = int(time.time())
        branch_name = f"{self.config.planner_branch_prefix}{timestamp}"

        return True, None, (branch_name, original_branch, original_head, autostash_id)

    def _validate_plan(self, plan: Plan, steps: List[PlanStep]) -> bool:
        """Validate plan structure and dependencies."""
        # Check for cycles in dependencies
        try:
            sorter = TopologicalSorter()
            for i, step in enumerate(plan.steps):
                deps = step.depends_on or []
                sorter.add(i, *deps)
            sorter.prepare()
        except ValueError:
            return False  # Cycle detected

        # Check file limits
        files_affected = len(set(step.file for step in steps))
        if files_affected > self.config.planner_max_files:
            return False

        return True

    def _create_branch(self, branch_name: str) -> bool:
        """Create and checkout new branch."""
        return self._run_git(["checkout", "-b", branch_name])

    def _apply_steps(self, plan: Plan, step_indices: List[int]) -> Tuple[List[str], List[PlanStep]]:
        """Apply selected steps."""
        commits = []
        applied_steps = []

        for idx in step_indices:
            step = plan.steps[idx]

            # Apply the step
            success, message = self._apply_single_step(step)
            if not success:
                # Revert last commit if any
                if commits:
                    self._run_git(["reset", "--hard", "HEAD~1"])
                return commits, applied_steps

            applied_steps.append(step)

            # Commit if configured
            if self.config.planner_checkpoint_commit_per_file:
                commit_msg = f"{step.intent}: {step.file} — {step.explanation}"
                if self._run_git(["add", step.file]):
                    commit_result = self._run_git(["commit", "-m", commit_msg])
                    if commit_result:
                        commit_sha = self._get_current_commit()
                        if commit_sha:
                            commits.append(commit_sha)

            # Run tests if required
            if self.config.planner_require_green_tests:
                if not self._run_tests():
                    # Revert last commit
                    if commits:
                        self._run_git(["reset", "--hard", "HEAD~1"])
                        commits.pop()
                    return commits, applied_steps

        # Final commit if not per-file
        if not self.config.planner_checkpoint_commit_per_file and applied_steps:
            self._run_git(["add", "."])
            commit_msg = f"Apply plan {plan.plan_id}: {plan.title}"
            commit_result = self._run_git(["commit", "-m", commit_msg])
            if commit_result:
                commit_sha = self._get_current_commit()
                if commit_sha:
                    commits.append(commit_sha)

        return commits, applied_steps

    def _apply_single_step(self, step: PlanStep) -> Tuple[bool, str]:
        """Apply a single plan step."""
        file_path = Path.cwd() / step.file

        if step.intent == "create":
            # For create, we need to generate content
            # This would use AI to generate the file content
            # For now, placeholder
            return True, "Create not fully implemented"

        elif step.intent == "delete":
            if file_path.exists():
                file_path.unlink()
            return True, f"Deleted {step.file}"

        elif step.intent == "rename":
            # Use git mv
            new_file = step.constraints.get("new_name") if step.constraints else None
            if new_file:
                return self._run_git(["mv", step.file, new_file]), f"Renamed {step.file} to {new_file}"
            return False, "Rename requires new_name in constraints"

        elif step.intent == "modify":
            # For modify, we need the diff
            # This would use existing diff generation
            # For now, placeholder
            return True, "Modify not fully implemented"

        return False, f"Unknown intent: {step.intent}"

    def _finalize(self, applied_info: AppliedPlanInfo) -> None:
        """Finalize the applied plan."""
        # Save applied info
        self.applied_dir.mkdir(parents=True, exist_ok=True)
        applied_file = self.applied_dir / f"{applied_info.plan_id}.json"

        with open(applied_file, 'w', encoding='utf-8') as f:
            json.dump({
                "plan_id": applied_info.plan_id,
                "branch_name": applied_info.branch_name,
                "original_branch": applied_info.original_branch,
                "original_head": applied_info.original_head,
                "commits": applied_info.commits,
                "applied_at": applied_info.applied_at,
                "total_files": applied_info.total_files,
                "total_changed_lines": applied_info.total_changed_lines,
                "autostash_id": applied_info.autostash_id
            }, f, indent=2)

        # Log to history
        plan_obj = self.planner.load_plan(applied_info.plan_id)
        title = plan_obj.title if plan_obj else ""
        history.add_plan_entry(
            plan_id=applied_info.plan_id,
            title=title,
            steps_count=applied_info.total_files,
            commits=applied_info.commits
        )

    def _load_applied_info(self, plan_id: str) -> Optional[AppliedPlanInfo]:
        """Load applied plan info."""
        applied_file = self.applied_dir / f"{plan_id}.json"
        if not applied_file.exists():
            return None

        try:
            with open(applied_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return AppliedPlanInfo(**data)
        except (json.JSONDecodeError, OSError):
            return None

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> bool:
        """Run git command and return success."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=cwd or Path.cwd(),
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _run_git_output(self, args: List[str], cwd: Optional[Path] = None) -> Optional[str]:
        """Run git command and return output."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=cwd or Path.cwd(),
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (subprocess.SubprocessError, FileNotFoundError):
            return None

    def _is_git_repo(self) -> bool:
        """Check if current directory is a git repo."""
        return self._run_git(["rev-parse", "--git-dir"])

    def _get_current_branch(self) -> Optional[str]:
        """Get current branch name."""
        return self._run_git_output(["branch", "--show-current"])

    def _get_current_commit(self, cwd: Optional[Path] = None) -> Optional[str]:
        """Get current commit SHA."""
        return self._run_git_output(["rev-parse", "HEAD"], cwd=cwd)

    def _is_working_tree_dirty(self) -> bool:
        """Check if working tree has uncommitted changes."""
        status = self._run_git_output(["status", "--porcelain"])
        return bool(status)

    def _estimate_changed_lines(self, step: PlanStep) -> int:
        """Estimate changed lines for a step."""
        # Placeholder - would analyze diff
        return 10

    def apply_plan_playground(self, plan: Plan, selected_steps: Optional[List[int]] = None) -> Tuple[bool, str, Optional[PlaygroundInfo]]:
        """
        Apply a plan in a detached git worktree (playground mode).

        Args:
            plan: The plan to apply.
            selected_steps: Indices of steps to apply (None for all).

        Returns:
            (success, message, playground_info)
        """
        try:
            # Create worktree
            worktree_path, branch_name, original_head = self._create_playground_worktree(plan.plan_id)
            if not worktree_path:
                return False, "Failed to create playground worktree", None

            # Apply steps in worktree
            commits, applied_steps, test_results = self._apply_steps_in_worktree(
                plan, selected_steps or list(range(len(plan.steps))), worktree_path
            )

            # Create playground info
            playground_info = PlaygroundInfo(
                plan_id=plan.plan_id,
                worktree_path=worktree_path,
                branch_name=branch_name,
                original_head=original_head,
                created_at=time.time(),
                commits=commits,
                total_files=len(set(step.file for step in applied_steps)),
                total_changed_lines=sum(self._estimate_changed_lines(step) for step in applied_steps),
                test_results=test_results
            )

            self._save_playground_info(playground_info)

            return True, f"Plan {plan.plan_id} applied in playground worktree at {worktree_path}", playground_info

        except Exception as e:
            return False, f"Playground application failed: {e}", None

    def promote_playground(self, plan_id: str, mode: str = "apply_patches") -> Tuple[bool, str]:
        """
        Promote a playground worktree to main repo.

        Args:
            plan_id: Plan ID.
            mode: "apply_patches" or "open_branch_only".

        Returns:
            (success, message)
        """
        playground_info = self._load_playground_info(plan_id)
        if not playground_info:
            return False, f"No playground info found for plan {plan_id}"

        try:
            if mode == "apply_patches":
                return self._promote_via_patches(playground_info)
            elif mode == "open_branch_only":
                return self._promote_via_branch(playground_info)
            else:
                return False, f"Unknown promote mode: {mode}"
        except Exception as e:
            return False, f"Promotion failed: {e}"

    def cleanup_playground(self, plan_id: str) -> Tuple[bool, str]:
        """
        Clean up a playground worktree.

        Args:
            plan_id: Plan ID.

        Returns:
            (success, message)
        """
        playground_info = self._load_playground_info(plan_id)
        if not playground_info:
            return False, f"No playground info found for plan {plan_id}"

        try:
            # Check for unmerged commits
            if playground_info.commits:
                # Check if branch has commits not in main
                if not self._run_git(["branch", "--contains", playground_info.commits[-1]]):
                    if not self.config.playground_keep_worktree_on_promote:
                        return False, "Worktree has unmerged commits, use promote first or set keep_worktree_on_promote"

            # Remove worktree
            if self._run_git(["worktree", "remove", str(playground_info.worktree_path)]):
                # Remove playground info
                playground_file = self.plans_dir / "playgrounds" / f"{plan_id}.json"
                if playground_file.exists():
                    playground_file.unlink()
                return True, f"Playground {plan_id} cleaned up successfully"
            else:
                return False, "Failed to remove worktree"

        except Exception as e:
            return False, f"Cleanup failed: {e}"

    def _create_playground_worktree(self, plan_id: str) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
        """Create a detached git worktree for playground."""
        if not self._is_git_repo():
            return None, None, None

        # Get original HEAD
        original_head = self._get_current_commit()
        if not original_head:
            return None, None, None

        # Create worktree directory
        worktree_root = Path.cwd() / self.config.playground_root
        worktree_root.mkdir(parents=True, exist_ok=True)
        worktree_path = worktree_root / plan_id

        # Create worktree at original HEAD
        if not self._run_git(["worktree", "add", "-d", str(worktree_path), original_head]):
            return None, None, None

        # Create and checkout branch inside worktree
        branch_name = f"play/{plan_id}"
        if not self._run_git(["checkout", "-b", branch_name], cwd=worktree_path):
            # Cleanup on failure
            self._run_git(["worktree", "remove", str(worktree_path)])
            return None, None, None

        return worktree_path, branch_name, original_head

    def _apply_steps_in_worktree(self, plan: Plan, step_indices: List[int], worktree_path: Path) -> Tuple[List[str], List[PlanStep], Optional[str]]:
        """Apply steps in the worktree."""
        commits = []
        applied_steps = []
        test_results = None

        for idx in step_indices:
            step = plan.steps[idx]

            # Apply the step
            success, message = self._apply_single_step_in_worktree(step, worktree_path)
            if not success:
                return commits, applied_steps, test_results

            applied_steps.append(step)

            # Commit if configured
            if self.config.planner_checkpoint_commit_per_file:
                commit_msg = f"{step.intent}: {step.file} — {step.explanation}"
                if self._run_git(["add", step.file], cwd=worktree_path):
                    commit_result = self._run_git(["commit", "-m", commit_msg], cwd=worktree_path)
                    if commit_result:
                        commit_sha = self._get_current_commit(worktree_path)
                        if commit_sha:
                            commits.append(commit_sha)

            # Run tests if required
            if self.config.planner_require_green_tests:
                test_success, test_output = self._run_tests_in_worktree(worktree_path)
                test_results = test_output
                if not test_success:
                    return commits, applied_steps, test_results

        # Final commit if not per-file
        if not self.config.planner_checkpoint_commit_per_file and applied_steps:
            self._run_git(["add", "."], cwd=worktree_path)
            commit_msg = f"Apply plan {plan.plan_id}: {plan.title}"
            commit_result = self._run_git(["commit", "-m", commit_msg], cwd=worktree_path)
            if commit_result:
                commit_sha = self._get_current_commit(worktree_path)
                if commit_sha:
                    commits.append(commit_sha)

        return commits, applied_steps, test_results

    def _apply_single_step_in_worktree(self, step: PlanStep, worktree_path: Path) -> Tuple[bool, str]:
        """Apply a single plan step in worktree."""
        file_path = worktree_path / step.file

        if step.intent == "create":
            # For create, we need to generate content - placeholder
            return True, "Create not fully implemented"

        elif step.intent == "delete":
            if file_path.exists():
                file_path.unlink()
            return True, f"Deleted {step.file}"

        elif step.intent == "rename":
            new_file = step.constraints.get("new_name") if step.constraints else None
            if new_file:
                return self._run_git(["mv", step.file, new_file], cwd=worktree_path), f"Renamed {step.file} to {new_file}"
            return False, "Rename requires new_name in constraints"

        elif step.intent == "modify":
            # For modify, we need the diff - placeholder
            return True, "Modify not fully implemented"

        return False, f"Unknown intent: {step.intent}"

    def _run_tests_in_worktree(self, worktree_path: Path) -> Tuple[bool, str]:
        """Run tests in worktree."""
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "-q"],
                cwd=worktree_path,
                capture_output=True,
                text=True
            )
            return result.returncode == 0, result.stdout + result.stderr
        except (subprocess.SubprocessError, FileNotFoundError):
            return False, "Tests failed to run"

    def _promote_via_patches(self, playground_info: PlaygroundInfo) -> Tuple[bool, str]:
        """Promote by creating and applying patches."""
        try:
            # Create patches directory
            patches_dir = self.plans_dir / "applied" / playground_info.plan_id / "patches"
            patches_dir.mkdir(parents=True, exist_ok=True)

            # Generate patches
            patch_files = []
            for i, commit in enumerate(playground_info.commits):
                patch_file = patches_dir / f"{i:04d}-{commit[:7]}.patch"
                try:
                    with open(patch_file, 'w', encoding='utf-8') as f:
                        result = subprocess.run(
                            ["git", "format-patch", "-1", "--stdout", commit],
                            cwd=playground_info.worktree_path,
                            capture_output=True,
                            text=True
                        )
                        if result.returncode == 0:
                            f.write(result.stdout)
                            patch_files.append(patch_file)
                        else:
                            return False, f"Failed to generate patch for {commit}"
                except (subprocess.SubprocessError, OSError) as e:
                    return False, f"Failed to write patch file: {e}"

            # Apply patches to main repo
            promoted_branch = f"{self.config.playground_promote_branch_prefix}{playground_info.plan_id}"
            if not self._run_git(["checkout", "-b", promoted_branch]):
                return False, "Failed to create promoted branch"

            for patch_file in patch_files:
                if not self._run_git(["am", str(patch_file)]):
                    # Abort and cleanup
                    self._run_git(["am", "--abort"])
                    self._run_git(["checkout", "-"])  # back to previous
                    self._run_git(["branch", "-D", promoted_branch])
                    return False, f"Failed to apply patch {patch_file.name}"

            # Success
            if not self.config.playground_keep_worktree_on_promote:
                self.cleanup_playground(playground_info.plan_id)

            return True, f"Promoted to branch {promoted_branch} with {len(patch_files)} patches"

        except Exception as e:
            return False, f"Patch promotion failed: {e}"

    def _promote_via_branch(self, playground_info: PlaygroundInfo) -> Tuple[bool, str]:
        """Promote by checking out the playground branch."""
        promoted_branch = f"{self.config.playground_promote_branch_prefix}{playground_info.plan_id}"
        if self._run_git(["checkout", "-b", promoted_branch, f"refs/heads/{playground_info.branch_name}"]):
            if not self.config.playground_keep_worktree_on_promote:
                self.cleanup_playground(playground_info.plan_id)
            return True, f"Checked out promoted branch {promoted_branch}"
        else:
            return False, "Failed to checkout promoted branch"

    def _save_playground_info(self, playground_info: PlaygroundInfo) -> None:
        """Save playground info."""
        playgrounds_dir = self.plans_dir / "playgrounds"
        playgrounds_dir.mkdir(parents=True, exist_ok=True)
        playground_file = playgrounds_dir / f"{playground_info.plan_id}.json"

        with open(playground_file, 'w', encoding='utf-8') as f:
            json.dump({
                "plan_id": playground_info.plan_id,
                "worktree_path": str(playground_info.worktree_path),
                "branch_name": playground_info.branch_name,
                "original_head": playground_info.original_head,
                "created_at": playground_info.created_at,
                "commits": playground_info.commits,
                "total_files": playground_info.total_files,
                "total_changed_lines": playground_info.total_changed_lines,
                "test_results": playground_info.test_results
            }, f, indent=2)

    def _load_playground_info(self, plan_id: str) -> Optional[PlaygroundInfo]:
        """Load playground info."""
        playground_file = self.plans_dir / "playgrounds" / f"{plan_id}.json"
        if not playground_file.exists():
            return None

        try:
            with open(playground_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data["worktree_path"] = Path(data["worktree_path"])
            return PlaygroundInfo(**data)
        except (json.JSONDecodeError, OSError):
            return None