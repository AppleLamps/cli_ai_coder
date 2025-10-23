"""Tests for partial patch application."""

import pytest
from editor.diffview import split_hunks, apply_selected_hunks, Hunk


def test_split_hunks_basic():
    """Test basic hunk splitting."""
    diff = """diff --git a/file.py b/file.py
index 1234567..abcdef0 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
 def old_func():
-    print("old")
+    print("new")
 def other_func():
     pass
@@ -10,3 +10,3 @@
 def another_func():
-    return 1
+    return 2"""

    hunks = split_hunks(diff)
    assert len(hunks) == 2
    assert hunks[0].filename == "file.py"
    assert hunks[0].start_line == 1
    assert hunks[1].start_line == 10


def test_split_hunks_no_hunks():
    """Test splitting when no hunks are present."""
    diff = """diff --git a/file.py b/file.py
index 1234567..abcdef0 100644
--- a/file.py
+++ b/file.py"""

    hunks = split_hunks(diff)
    assert len(hunks) == 0


def test_apply_selected_hunks_all():
    """Test applying all hunks."""
    text_by_path = {
        "file.py": """def old_func():
    print("old")
def other_func():
    pass
def another_func():
    return 1"""
    }

    diff = """diff --git a/file.py b/file.py
index 1234567..abcdef0 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
 def old_func():
-    print("old")
+    print("new")
 def other_func():
     pass
@@ -6,3 +6,3 @@
 def another_func():
-    return 1
+    return 2"""

    hunks = split_hunks(diff)
    for hunk in hunks:
        hunk.selected = True

    result = apply_selected_hunks(text_by_path, hunks)
    assert 'print("new")' in result["file.py"]
    assert "return 2" in result["file.py"]


def test_apply_selected_hunks_partial():
    """Test applying only selected hunks."""
    text_by_path = {
        "file.py": """def old_func():
    print("old")
def other_func():
    pass
def another_func():
    return 1"""
    }

    diff = """diff --git a/file.py b/file.py
index 1234567..abcdef0 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
 def old_func():
-    print("old")
+    print("new")
 def other_func():
     pass
@@ -6,3 +6,3 @@
 def another_func():
-    return 1
+    return 2"""

    hunks = split_hunks(diff)
    hunks[0].selected = True  # Select only first hunk

    result = apply_selected_hunks(text_by_path, hunks)
    assert 'print("new")' in result["file.py"]
    assert "return 1" in result["file.py"]  # Second hunk not applied


def test_apply_selected_hunks_none():
    """Test applying no hunks."""
    text_by_path = {
        "file.py": """def old_func():
    print("old")
def other_func():
    pass"""
    }

    diff = """diff --git a/file.py b/file.py
index 1234567..abcdef0 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
 def old_func():
-    print("old")
+    print("new")
 def other_func():
     pass"""

    hunks = split_hunks(diff)
    # No hunks selected

    result = apply_selected_hunks(text_by_path, hunks)
    assert result["file.py"] == text_by_path["file.py"]