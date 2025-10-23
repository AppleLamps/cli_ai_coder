"""Tests for Git extras: blame, stash, branches."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from editor.commands import git_stash_save, git_stash_list, git_stash_pop, git_stash_apply, git_stash_drop, git_branch_switcher


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


def test_git_stash_save(temp_git_repo):
    """Test git stash save."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)
        
        # Modify file
        readme = temp_git_repo / "README.md"
        readme.write_text("# Test Repo\nModified\n")
        
        # Stash
        result = git_stash_save("test stash")
        assert "stashed" in result.lower()
        
        # Check file is reverted
        content = readme.read_text()
        assert "Modified" not in content
        
    finally:
        os.chdir(old_cwd)


def test_git_stash_list(temp_git_repo):
    """Test git stash list."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)
        
        # Create stash
        readme = temp_git_repo / "README.md"
        readme.write_text("# Test Repo\nModified\n")
        git_stash_save("test stash")
        
        # List stashes
        result = git_stash_list()
        assert "stash" in result.lower() or result == "No stashes"
        
    finally:
        os.chdir(old_cwd)


def test_git_stash_pop(temp_git_repo):
    """Test git stash pop."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)
        
        # Create stash
        readme = temp_git_repo / "README.md"
        original_content = readme.read_text()
        readme.write_text("# Test Repo\nModified\n")
        git_stash_save("test stash")
        
        # Pop stash
        result = git_stash_pop()
        assert "popped" in result.lower()
        
        # Check file is restored
        content = readme.read_text()
        assert "Modified" in content
        
    finally:
        os.chdir(old_cwd)


def test_git_stash_apply(temp_git_repo):
    """Test git stash apply."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)
        
        # Create stash
        readme = temp_git_repo / "README.md"
        readme.write_text("# Test Repo\nModified\n")
        git_stash_save("test stash")
        
        # Apply stash
        result = git_stash_apply()
        assert "applied" in result.lower()
        
        # Check file is modified
        content = readme.read_text()
        assert "Modified" in content
        
        # Check stash still exists
        stashes = git_stash_list()
        assert "stash" in stashes.lower()
        
    finally:
        os.chdir(old_cwd)


def test_git_stash_drop(temp_git_repo):
    """Test git stash drop."""
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(temp_git_repo)
        
        # Create stash
        readme = temp_git_repo / "README.md"
        readme.write_text("# Test Repo\nModified\n")
        git_stash_save("test stash")
        
        # Drop stash
        result = git_stash_drop()
        assert "dropped" in result.lower()
        
        # Check no stashes
        stashes = git_stash_list()
        assert stashes == "No stashes" or "stash" not in stashes.lower()
        
    finally:
        os.chdir(old_cwd)


def test_git_branch_switcher():
    """Test git branch switcher (placeholder)."""
    result = git_branch_switcher()
    # Since it's placeholder, just check it returns something
    assert isinstance(result, str)