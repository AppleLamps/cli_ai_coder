"""Unified diff application utilities."""

import re
from typing import Dict, List, Set


def is_unified_diff(text: str) -> bool:
    """
    Check if the given text contains a unified diff.

    Args:
        text: The text to check.

    Returns:
        True if the text appears to be a unified diff, False otherwise.
    """
    lines = text.splitlines()
    # Look for diff markers
    has_diff_start = any(line.startswith('--- ') for line in lines)
    has_diff_end = any(line.startswith('+++ ') for line in lines)
    has_hunk = any(line.startswith('@@ ') for line in lines)

    return has_diff_start and has_diff_end and has_hunk


def parse_affected_paths(diff: str) -> Set[str]:
    """
    Parse the paths affected by a unified diff.

    Args:
        diff: The unified diff string.

    Returns:
        Set of affected file paths.
    """
    paths = set()
    lines = diff.splitlines()

    for line in lines:
        if line.startswith('+++ '):
            path = line[4:].strip()
            # Remove any trailing timestamp info
            if '\t' in path:
                path = path.split('\t')[0]
            paths.add(path)

    return paths


def split_hunks(diff: str) -> List[Dict]:
    """
    Split a unified diff into individual hunks.

    Args:
        diff: The unified diff string.

    Returns:
        List of hunk dictionaries with filename, start_line, content, selected.
    """
    hunks = []
    lines = diff.splitlines()
    i = 0

    while i < len(lines):
        if lines[i].startswith('+++ '):
            filename = lines[i][4:].strip()
            if filename.startswith('b/'):
                filename = filename[2:]
            i += 1

            # Skip to first hunk
            while i < len(lines) and not lines[i].startswith('@@'):
                i += 1

            while i < len(lines) and lines[i].startswith('@@'):
                # Parse hunk header @@ -old_start,old_len +new_start,new_len @@
                match = re.match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', lines[i])
                if match:
                    new_start = int(match.group(3))

                    # Collect hunk content
                    i += 1
                    hunk_lines = []
                    while i < len(lines) and not lines[i].startswith('@@') and not lines[i].startswith('+++'):
                        hunk_lines.append(lines[i])
                        i += 1

                    hunk_content = '\n'.join(hunk_lines)
                    hunks.append({
                        'filename': filename,
                        'start_line': new_start,
                        'content': hunk_content,
                        'selected': False
                    })
                else:
                    i += 1
        else:
            i += 1

    return hunks


def apply_selected_hunks(text_by_path: Dict[str, str], hunks: List[Dict]) -> Dict[str, str]:
    """
    Apply only the selected hunks to the texts.

    Args:
        text_by_path: Dict of filename to current content.
        hunks: List of hunk dicts to apply (only selected ones will be applied).

    Returns:
        Dict of filename to updated content.
    """
    # Filter selected hunks
    selected_hunks = [h for h in hunks if h.get('selected', False)]

    # Create mini-diffs for each selected hunk
    mini_diffs = []
    for hunk in selected_hunks:
        filename = hunk['filename']
        # Create a minimal diff with just this hunk
        mini_diff = f"""--- a/{filename}
+++ b/{filename}
@@ -{hunk['start_line']},0 +{hunk['start_line']},0 @@
{hunk['content']}
"""
        mini_diffs.append(mini_diff)

    # Apply all mini-diffs
    updated = text_by_path.copy()
    for mini_diff in mini_diffs:
        try:
            updated = apply_unified_diff(updated, mini_diff)
        except Exception:
            # If a hunk fails to apply, skip it
            continue

    return updated


def apply_unified_diff(text_by_path: Dict[str, str], diff: str) -> Dict[str, str]:
    """
    Apply a unified diff to the given texts.

    Args:
        text_by_path: Dict of filename to current content.
        diff: The unified diff string.

    Returns:
        Dict of filename to updated content.

    Raises:
        ValueError: If the diff is malformed or cannot be applied.
    """
    updated = text_by_path.copy()
    lines = diff.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith('+++ '):
            filename = lines[i][4:].strip()
            if filename not in updated:
                updated[filename] = ""
            i += 1
            # Skip to hunk
            while i < len(lines) and not lines[i].startswith('@@'):
                i += 1
            if i >= len(lines):
                break
            # Parse hunk header @@ -old_start,old_len +new_start,new_len @@
            match = re.match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', lines[i])
            if not match:
                raise ValueError(f"Invalid hunk header: {lines[i]}")
            old_start = int(match.group(1))
            old_len = int(match.group(2)) if match.group(2) else 1
            new_start = int(match.group(3))
            new_len = int(match.group(4)) if match.group(4) else 1
            i += 1
            # Collect hunk lines
            hunk_lines = []
            while i < len(lines) and not lines[i].startswith('@@') and not lines[i].startswith('+++'):
                hunk_lines.append(lines[i])
                i += 1
            # Apply hunk (simplified: replace old lines with new lines from hunk)
            text = updated[filename]
            text_lines = text.splitlines()
            
            # Extract old and new lines from hunk
            old_lines = []
            new_lines = []
            for line in hunk_lines:
                if line.startswith(' '):
                    old_lines.append(line[1:])
                    new_lines.append(line[1:])
                elif line.startswith('-'):
                    old_lines.append(line[1:])
                elif line.startswith('+'):
                    new_lines.append(line[1:])
            
            # Replace the old lines with new lines
            # This is a very simplified implementation
            old_text = '\n'.join(old_lines)
            new_text = '\n'.join(new_lines)
            
            if old_text in text:
                updated[filename] = text.replace(old_text, new_text, 1)
            else:
                # If exact match not found, try line-by-line replacement
                start_idx = old_start - 1
                end_idx = start_idx + old_len
                if start_idx < len(text_lines):
                    text_lines = text_lines[:start_idx] + new_lines + text_lines[end_idx:]
                    updated[filename] = '\n'.join(text_lines)
    
    return updated