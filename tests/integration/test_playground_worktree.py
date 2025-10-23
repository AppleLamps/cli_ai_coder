"""Integration tests for playground worktree mode."""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ai.plan_executor import PlanExecutor, PlaygroundInfo
from ai.planner import Plan, PlanStep


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)

        # Create initial files and commit
        file1 = repo_path / "file1.py"
        file1.write_text("print('hello')\n")
        file2 = repo_path / "file2.py"
        file2.write_text("print('world')\n")
        test_file = repo_path / "test_example.py"
        test_file.write_text("""
def test_example():
    assert True
""")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

        yield repo_path


def test_playground_apply_flow(temp_git_repo):
    """Test the full playground apply flow."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)

        # Create a simple plan
        plan = Plan(
            title="Test Playground Plan",
            rationale="Test playground application",
            steps=[
                PlanStep(
                    file="file1.py",
                    intent="modify",
                    explanation="Modify file1",
                    constraints={}
                ),
                PlanStep(
                    file="file2.py",
                    intent="modify",
                    explanation="Modify file2",
                    constraints={}
                )
            ],
            created_at=0,
            plan_id="test_playground_123"
        )

        # Mock the AI diff generation
        def mock_apply_single_step_in_worktree(step, worktree_path):
            file_path = worktree_path / step.file
            if step.file == "file1.py":
                content = file_path.read_text()
                new_content = content.replace("print('hello')", "print('hello playground')")
                file_path.write_text(new_content)
            elif step.file == "file2.py":
                content = file_path.read_text()
                new_content = content.replace("print('world')", "print('world playground')")
                file_path.write_text(new_content)
            return True, f"Modified {step.file}"

        executor = PlanExecutor()

        # Mock the apply_single_step_in_worktree
        with patch.object(executor, '_apply_single_step_in_worktree', side_effect=mock_apply_single_step_in_worktree):
            success, message, playground_info = executor.apply_plan_playground(plan)

        assert success, f"Playground apply failed: {message}"
        assert playground_info is not None
        assert isinstance(playground_info, PlaygroundInfo)
        assert "test_playground_123" in message
        assert isinstance(playground_info, PlaygroundInfo)

        # Check that worktree exists
        assert playground_info.worktree_path.exists()
        assert (playground_info.worktree_path / "file1.py").exists()
        assert (playground_info.worktree_path / "file2.py").exists()

        # Check that worktree has modifications
        content1 = (playground_info.worktree_path / "file1.py").read_text()
        content2 = (playground_info.worktree_path / "file2.py").read_text()
        assert "playground" in content1
        assert "playground" in content2

        # Check that main repo is untouched
        main_content1 = (temp_git_repo / "file1.py").read_text()
        main_content2 = (temp_git_repo / "file2.py").read_text()
        assert "playground" not in main_content1
        assert "playground" not in main_content2

        # Check that playground info was saved
        playground_file = temp_git_repo / ".cli_ai_coder" / "plans" / "playgrounds" / "test_playground_123.json"
        assert playground_file.exists()

        with open(playground_file, 'r') as f:
            data = json.load(f)
        assert data["plan_id"] == "test_playground_123"
        assert data["branch_name"] == "play/test_playground_123"
        assert len(data["commits"]) >= 1

    finally:
        os.chdir(old_cwd)


def test_playground_promote_via_patches(temp_git_repo):
    """Test promoting playground via patches."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)

        # First create a playground
        plan = Plan(
            title="Test Promote Plan",
            rationale="Test promote",
            steps=[
                PlanStep(
                    file="file1.py",
                    intent="modify",
                    explanation="Modify file1",
                    constraints={}
                )
            ],
            created_at=0,
            plan_id="test_promote_123"
        )

        executor = PlanExecutor()

        def mock_apply_single_step_in_worktree(step, worktree_path):
            file_path = worktree_path / step.file
            content = file_path.read_text()
            new_content = content.replace("print('hello')", "print('hello promoted')")
            file_path.write_text(new_content)
            return True, f"Modified {step.file}"

        with patch.object(executor, '_apply_single_step_in_worktree', side_effect=mock_apply_single_step_in_worktree):
            success, message, playground_info = executor.apply_plan_playground(plan)
        assert success
        assert playground_info is not None
        assert isinstance(playground_info, PlaygroundInfo)

        # Now promote via patches
        success, message = executor.promote_playground("test_promote_123", "apply_patches")
        assert success, f"Promote failed: {message}"

        # Check that promoted branch exists
        result = subprocess.run(["git", "branch", "--list"], cwd=temp_git_repo, capture_output=True, text=True)
        branches = result.stdout.strip()
        assert "ai/promoted/test_promote_123" in branches

        # Check that patches directory exists
        patches_dir = temp_git_repo / ".cli_ai_coder" / "plans" / "applied" / "test_promote_123" / "patches"
        assert patches_dir.exists()
        patch_files = list(patches_dir.glob("*.patch"))
        assert len(patch_files) >= 1

        # Check that changes are applied in promoted branch
        subprocess.run(["git", "checkout", "ai/promoted/test_promote_123"], cwd=temp_git_repo, check=True)
        promoted_content = (temp_git_repo / "file1.py").read_text()
        assert "promoted" in promoted_content

        # Check that worktree is cleaned up (since keep_worktree_on_promote is False by default)
        playground_info_after = executor._load_playground_info("test_promote_123")
        if playground_info_after is None:  # Worktree was cleaned up
            assert not playground_info.worktree_path.exists()
        else:
            # Worktree kept
            assert playground_info.worktree_path.exists()

    finally:
        os.chdir(old_cwd)


def test_playground_cleanup(temp_git_repo):
    """Test playground cleanup."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)

        # Create a playground
        plan = Plan(
            title="Test Cleanup Plan",
            rationale="Test cleanup",
            steps=[
                PlanStep(
                    file="file1.py",
                    intent="modify",
                    explanation="Modify file1",
                    constraints={}
                )
            ],
            created_at=0,
            plan_id="test_cleanup_123"
        )

        executor = PlanExecutor()

        def mock_apply_single_step_in_worktree(step, worktree_path):
            file_path = worktree_path / step.file
            content = file_path.read_text()
            new_content = content.replace("print('hello')", "print('hello cleanup')")
            file_path.write_text(new_content)
            return True, f"Modified {step.file}"

        with patch.object(executor, '_apply_single_step_in_worktree', side_effect=mock_apply_single_step_in_worktree):
            success, message, playground_info = executor.apply_plan_playground(plan)
        assert success
        assert playground_info is not None
        assert isinstance(playground_info, PlaygroundInfo)

        # Verify worktree exists
        assert playground_info.worktree_path.exists()

        # Now cleanup
        success, message = executor.cleanup_playground("test_cleanup_123")
        assert success, f"Cleanup failed: {message}"

        # Check that worktree is removed
        assert not playground_info.worktree_path.exists()

        # Check that playground info is removed
        playground_file = temp_git_repo / ".cli_ai_coder" / "plans" / "playgrounds" / "test_cleanup_123.json"
        assert not playground_file.exists()

    finally:
        os.chdir(old_cwd)