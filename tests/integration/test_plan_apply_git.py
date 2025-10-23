"""Integration tests for plan application with Git integration."""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ai.plan_executor import PlanExecutor
from ai.planner import Plan, PlanStep
from ai.history import history


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


def test_plan_apply_flow(temp_git_repo):
    """Test the full plan apply flow."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)

        # Create a simple plan
        plan = Plan(
            title="Test Plan",
            rationale="Test plan application",
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
            plan_id="test_plan_123"
        )

        # Mock the AI diff generation
        def mock_apply_single_step(step):
            file_path = Path.cwd() / step.file
            if step.file == "file1.py":
                content = file_path.read_text()
                new_content = content.replace("print('hello')", "print('hello modified')")
                file_path.write_text(new_content)
            elif step.file == "file2.py":
                content = file_path.read_text()
                new_content = content.replace("print('world')", "print('world modified')")
                file_path.write_text(new_content)
            return True, f"Modified {step.file}"

        executor = PlanExecutor()

        # Mock the apply_single_step
        with patch.object(executor, '_apply_single_step', side_effect=mock_apply_single_step):
            success, message = executor.apply_plan(plan)

        assert success, f"Plan apply failed: {message}"
        assert "test_plan_123" in message

        # Check that new branch was created
        result = subprocess.run(["git", "branch", "--show-current"], cwd=temp_git_repo, capture_output=True, text=True)
        current_branch = result.stdout.strip()
        assert "ai/plan-" in current_branch

        # Check that commits were made
        result = subprocess.run(["git", "log", "--oneline", "-n", "10"], cwd=temp_git_repo, capture_output=True, text=True)
        commits = result.stdout.strip().splitlines()
        assert len(commits) >= 2  # At least initial + final commit

        # Check that files were modified
        assert "modified" in (temp_git_repo / "file1.py").read_text()
        assert "modified" in (temp_git_repo / "file2.py").read_text()

        # Check that applied info was saved
        applied_file = temp_git_repo / ".cli_ai_coder" / "plans" / "applied" / "test_plan_123.json"
        assert applied_file.exists()

        with open(applied_file, 'r') as f:
            data = json.load(f)
        assert data["plan_id"] == "test_plan_123"
        assert data["branch_name"] == current_branch
        assert len(data["commits"]) >= 1

    finally:
        os.chdir(old_cwd)


def test_plan_apply_with_test_gating(temp_git_repo):
    """Test plan apply with test gating."""
    # TODO: Implement test gating test when config mocking is easier
    pass


def test_plan_rollback(temp_git_repo):
    """Test plan rollback."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)

        # First apply a plan
        plan = Plan(
            title="Test Plan",
            rationale="Test rollback",
            steps=[
                PlanStep(
                    file="file1.py",
                    intent="modify",
                    explanation="Modify file1",
                    constraints={}
                )
            ],
            created_at=0,
            plan_id="test_plan_rollback"
        )

        executor = PlanExecutor()

        def mock_apply_single_step(step):
            file_path = Path.cwd() / step.file
            content = file_path.read_text()
            new_content = content.replace("print('hello')", "print('hello modified')")
            file_path.write_text(new_content)
            return True, f"Modified {step.file}"

        with patch.object(executor, '_apply_single_step', side_effect=mock_apply_single_step):
            success, message = executor.apply_plan(plan)
        assert success

        # Get current branch and file state
        result = subprocess.run(["git", "branch", "--show-current"], cwd=temp_git_repo, capture_output=True, text=True)
        applied_branch = result.stdout.strip()
        original_content = (temp_git_repo / "file1.py").read_text()

        # Now rollback
        success, message = executor.rollback_plan("test_plan_rollback")
        assert success, f"Rollback failed: {message}"

        # Check we're back on original branch
        result = subprocess.run(["git", "branch", "--show-current"], cwd=temp_git_repo, capture_output=True, text=True)
        current_branch = result.stdout.strip()
        assert current_branch != applied_branch

        # Check file content is reverted
        reverted_content = (temp_git_repo / "file1.py").read_text()
        assert "modified" not in reverted_content

        # Check applied file is removed
        applied_file = temp_git_repo / ".cli_ai_coder" / "plans" / "applied" / "test_plan_rollback.json"
        assert not applied_file.exists()

    finally:
        os.chdir(old_cwd)