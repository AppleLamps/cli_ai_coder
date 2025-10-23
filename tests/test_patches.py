"""Tests for patches module."""

import pytest

from ai.patches import apply_unified_diff


def test_apply_unified_diff_add_line():
    """Test adding a line."""
    text_by_path = {"file.txt": "line1\nline2\nline3"}
    diff = """+++ file.txt
@@ -1,3 +1,4 @@
 line1
 line2
+new line
 line3
"""
    result = apply_unified_diff(text_by_path, diff)
    expected = "line1\nline2\nnew line\nline3"
    assert result["file.txt"] == expected


def test_apply_unified_diff_remove_line():
    """Test removing a line."""
    text_by_path = {"file.txt": "line1\nline2\nline3"}
    diff = """+++ file.txt
@@ -1,3 +1,2 @@
 line1
-line2
 line3
"""
    result = apply_unified_diff(text_by_path, diff)
    expected = "line1\nline3"
    assert result["file.txt"] == expected


def test_apply_unified_diff_change_line():
    """Test changing a line."""
    text_by_path = {"file.txt": "line1\nline2\nline3"}
    diff = """+++ file.txt
@@ -1,3 +1,3 @@
 line1
-line2
+changed
 line3
"""
    result = apply_unified_diff(text_by_path, diff)
    expected = "line1\nchanged\nline3"
    assert result["file.txt"] == expected


def test_apply_unified_diff_invalid_hunk():
    """Test invalid hunk header."""
    text_by_path = {"file.txt": "content"}
    diff = """+++ file.txt
@@ invalid @@
"""
    with pytest.raises(ValueError):
        apply_unified_diff(text_by_path, diff)