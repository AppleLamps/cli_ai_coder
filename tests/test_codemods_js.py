"""Tests for JavaScript/TypeScript codemods."""

import pytest
from codemods.js_ts import RenameExportCodemod, RemoveConsoleCodemod, OrganizeImportsBestEffortCodemod


class TestRenameExportCodemod:
    """Test rename export codemod."""

    def test_preview_rename_export(self):
        """Test preview of renaming an export."""
        code = 'export { oldName };'
        mod = RenameExportCodemod("oldName", "newName")
        diff = mod.preview("test.js", code)
        assert "oldName" in diff
        assert "newName" in diff

    def test_apply_rename_export(self):
        """Test applying export rename."""
        code = 'export { oldName };'
        expected = 'export { newName };'
        mod = RenameExportCodemod("oldName", "newName")
        result = mod.apply("test.js", code)
        assert "oldName" not in result
        assert "newName" in result


class TestRemoveConsoleCodemod:
    """Test remove console codemod."""

    def test_preview_remove_console_log(self):
        """Test preview of removing console.log."""
        code = 'console.log("Hello");'
        mod = RemoveConsoleCodemod()
        diff = mod.preview("test.js", code)
        assert "console.log" in diff

    def test_apply_remove_console_log(self):
        """Test applying console.log removal."""
        code = 'console.log("Hello");\nconst x = 1;'
        expected = 'const x = 1;'
        mod = RemoveConsoleCodemod()
        result = mod.apply("test.js", code)
        assert "console.log" not in result
        assert "const x = 1;" in result


class TestOrganizeImportsBestEffortCodemod:
    """Test organize imports codemod."""

    def test_preview_organize_imports(self):
        """Test preview of organizing imports."""
        code = """
import { b } from 'lib';
import { a } from 'lib';
const x = 1;
"""
        mod = OrganizeImportsBestEffortCodemod()
        diff = mod.preview("test.js", code)
        # Should reorder imports
        assert "import" in diff

    def test_apply_organize_imports(self):
        """Test applying import organization."""
        code = """
import { b } from 'lib';
import { a } from 'lib';
const x = 1;
"""
        mod = OrganizeImportsBestEffortCodemod()
        result = mod.apply("test.js", code)
        # Should have imports first, then code
        lines = result.strip().split('\n')
        assert lines[0].startswith('import')
        assert lines[-1] == 'const x = 1;'