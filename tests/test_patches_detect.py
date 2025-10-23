"""Tests for diff detection."""

from ai.patches import is_unified_diff, parse_affected_paths


def test_is_unified_diff_true():
    """Test detecting a valid unified diff."""
    diff = """--- file.txt
+++ file.txt
@@ -1,3 +1,4 @@
 line1
 line2
+new line
 line3
"""
    assert is_unified_diff(diff) is True


def test_is_unified_diff_false():
    """Test rejecting plain text as diff."""
    text = "This is just some plain text explanation of the code."
    assert is_unified_diff(text) is False


def test_parse_affected_paths():
    """Test parsing affected paths from diff."""
    diff = """+++ src/main.py
@@ -1,3 +1,4 @@
 line1
 line2
+new line
 line3
+++ tests/test_main.py
@@ -1,2 +1,3 @@
 test1
+test2
 test3
"""
    paths = parse_affected_paths(diff)
    expected = {"src/main.py", "tests/test_main.py"}
    assert paths == expected