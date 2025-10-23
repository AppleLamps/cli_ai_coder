"""Tests for Git integration."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from editor.gutter import GitStatusGutter
from editor.commands import git_status, git_diff, git_stage, git_unstage, git_commit


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
        
        # Create initial commit
        readme = repo_path / "README.md"
        readme.write_text("# Test Repo\n")
        subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)
        
        yield repo_path


def test_git_status_gutter_no_repo():
    """Test gutter when not in a git repo."""
    gutter = GitStatusGutter()
    assert not gutter.is_git_repo()
    
    # Test with non-existent file
    marks = gutter.get_status_marks(Path("/nonexistent/file.py"))
    assert marks == []


def test_git_status_gutter_clean_repo(temp_git_repo):
    """Test gutter in a clean repo."""
    # Change to temp repo directory
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)
        gutter = GitStatusGutter()
        assert gutter.is_git_repo()
        
        # Check existing file
        marks = gutter.get_status_marks(temp_git_repo / "README.md")
        assert marks == []  # Clean file
        
    finally:
        os.chdir(old_cwd)


def test_git_status_gutter_modified_file(temp_git_repo):
    """Test gutter with modified file."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)
        
        # Modify file
        readme = temp_git_repo / "README.md"
        readme.write_text("# Test Repo\nModified content\n")
        
        gutter = GitStatusGutter()
        marks = gutter.get_status_marks(readme)
        
        # Should have modification marks
        assert len(marks) > 0
        # Check that marks are tuples of (line_num, mark)
        for line_num, mark in marks:
            assert isinstance(line_num, int)
            assert mark in ['A', 'M', 'D']
            
    finally:
        os.chdir(old_cwd)


def test_git_commands_no_repo():
    """Test git commands when not in a repo."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(Path.home())  # Assume home is not a git repo
        
        assert "not a git repository" in git_status().lower() or "not available" in git_status().lower()
        assert "not a git repository" in git_diff().lower() or "failed" in git_diff().lower()
        assert "not a git repository" in git_stage().lower() or "not available" in git_stage().lower()
        assert "not a git repository" in git_unstage().lower() or "not available" in git_unstage().lower()
        assert "not a git repository" in git_commit("test").lower() or "not available" in git_commit("test").lower()
        
    finally:
        os.chdir(old_cwd)


def test_git_status_command(temp_git_repo):
    """Test git status command."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)
        
        # Clean repo
        result = git_status()
        assert "clean" in result.lower() or "nothing" in result.lower()
        
        # Modify file
        readme = temp_git_repo / "README.md"
        readme.write_text("# Test Repo\nModified\n")
        
        result = git_status()
        assert "modified" in result.lower() or "M" in result
        
    finally:
        os.chdir(old_cwd)


def test_git_stage_unstage_commit(temp_git_repo):
    """Test staging, unstaging, and committing."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)
        
        # Create new file
        new_file = temp_git_repo / "test.txt"
        new_file.write_text("test content")
        
        # Stage it
        result = git_stage("test.txt")
        assert "staged" in result.lower()
        
        # Check status
        status = git_status()
        assert "staged" in status.lower() or "A" in status
        
        # Unstage it
        result = git_unstage("test.txt")
        assert "unstaged" in result.lower()
        
        # Stage and commit
        git_stage("test.txt")
        result = git_commit("Add test file")
        assert "committed" in result.lower()
        
        # Verify clean
        status = git_status()
        assert "clean" in status.lower() or "nothing" in status.lower()
        
    finally:
        os.chdir(old_cwd)


def test_git_commit_empty_message():
    """Test commit with empty message."""
    result = git_commit("")
    assert "cannot be empty" in result.lower()
    
    result = git_commit("   ")
    assert "cannot be empty" in result.lower()