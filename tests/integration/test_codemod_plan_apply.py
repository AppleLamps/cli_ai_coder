"""Integration tests for codemod plan apply."""

import os
import pytest
import tempfile
import subprocess
from pathlib import Path
from codemods.python_libcst import RenameSymbolCodemod
from editor.ws_codemod import WorkspaceCodemodRunner


class TestCodemodPlanApply:
    """Test codemod integration with plan apply."""

    def test_codemod_with_plan_apply(self, tmp_path):
        """Test applying codemod via plan executor."""
        # Create test files
        file1 = tmp_path / "file1.py"
        file1.write_text("""
def old_func():
    return "test"

result = old_func()
""")

        file2 = tmp_path / "file2.py"
        file2.write_text("""
from file1 import old_func

value = old_func()
""")

        # Change to temp directory
        original_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_path)

            # Initialize git repo
            subprocess.run(["git", "init"], check=True, capture_output=True)
            subprocess.run(["git", "add", "."], check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], check=True, capture_output=True)

            # Create codemod
            mod = RenameSymbolCodemod("old_func", "new_func")

            # Generate targets
            runner = WorkspaceCodemodRunner()
            targets = runner.generate_diffs("rename_symbol", {"old_name": "old_func", "new_name": "new_func"}, ["file1.py", "file2.py"])

            # Should have changes
            assert len(targets) > 0

            # Apply via plan
            success = runner.apply_codemods(targets, "rename_symbol", {"old_name": "old_func", "new_name": "new_func"})
            assert success

            # Check files were modified
            content1 = file1.read_text()
            assert "old_func" not in content1
            assert "new_func" in content1

            content2 = file2.read_text()
            assert "old_func" not in content2
            assert "new_func" in content2

        finally:
            os.chdir(original_cwd)

    def test_codemod_noop_when_no_changes(self, tmp_path):
        """Test codemod produces no changes when not applicable."""
        # Create test file without target symbol
        file1 = tmp_path / "file1.py"
        file1.write_text("""
def other_func():
    return "test"
""")

        # Change to temp directory
        original_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_path)

            # Create codemod
            mod = RenameSymbolCodemod("old_func", "new_func")

            # Generate targets
            runner = WorkspaceCodemodRunner()
            targets = runner.generate_diffs("rename_symbol", {"old_name": "old_func", "new_name": "new_func"}, ["file1.py"])

            # Should have no changes
            assert len(targets) == 0

        finally:
            os.chdir(original_cwd)