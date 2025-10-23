"""Git status gutter for the editor."""

import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.config import get_config


class GitStatusGutter:
    """Shows git status marks (A/M/D) in the editor gutter."""

    def __init__(self):
        self.repo_root: Optional[Path] = None
        self.status_cache: Dict[str, List[Tuple[int, str]]] = {}
        self._find_repo_root()

    def _find_repo_root(self) -> None:
        """Find the git repository root."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                cwd=Path.cwd()
            )
            if result.returncode == 0:
                self.repo_root = Path(result.stdout.strip())
            else:
                self.repo_root = None
        except (subprocess.SubprocessError, FileNotFoundError):
            self.repo_root = None

    def is_git_repo(self) -> bool:
        """Check if current directory is a git repository."""
        return self.repo_root is not None

    def get_status_marks(self, file_path: Path) -> List[Tuple[int, str]]:
        """
        Get status marks for a file.

        Returns list of (line_number, mark) tuples where mark is 'A', 'M', or 'D'.
        """
        if not self.is_git_repo() or self.repo_root is None:
            return []

        # Use cached result if available
        cache_key = str(file_path.relative_to(self.repo_root))
        if cache_key in self.status_cache:
            return self.status_cache[cache_key]

        try:
            # Run git diff --unified=0 to get minimal diff
            result = subprocess.run(
                ["git", "diff", "--unified=0", "--", cache_key],
                capture_output=True,
                text=True,
                cwd=self.repo_root
            )

            marks = []
            if result.returncode == 0:
                marks = self._parse_diff_output(result.stdout)

            # Also check for untracked files
            if not marks:
                result = subprocess.run(
                    ["git", "status", "--porcelain", "--", cache_key],
                    capture_output=True,
                    text=True,
                    cwd=self.repo_root
                )
                if result.returncode == 0 and result.stdout.startswith("??"):
                    # Untracked file - all lines are additions
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        marks = [(i + 1, 'A') for i in range(len(lines))]
                    except (OSError, UnicodeDecodeError):
                        pass

            self.status_cache[cache_key] = marks
            return marks

        except (subprocess.SubprocessError, FileNotFoundError):
            return []

    def _parse_diff_output(self, diff_output: str) -> List[Tuple[int, str]]:
        """Parse git diff output to extract status marks."""
        marks = []
        lines = diff_output.splitlines()

        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith('@@'):
                # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
                parts = line.split()
                if len(parts) >= 3:
                    new_part = parts[2]  # +new_start,new_count
                    if new_part.startswith('+'):
                        try:
                            new_start = int(new_part[1:].split(',')[0])
                            # Look at the next lines for changes
                            i += 1
                            line_num = new_start
                            while i < len(lines) and not lines[i].startswith('@@'):
                                change_line = lines[i]
                                if change_line.startswith('+'):
                                    marks.append((line_num, 'A'))
                                    line_num += 1
                                elif change_line.startswith('-'):
                                    marks.append((line_num, 'D'))
                                    # Don't increment for deletions
                                elif change_line.startswith(' '):
                                    line_num += 1
                                i += 1
                            i -= 1  # Adjust for outer loop
                        except (ValueError, IndexError):
                            pass
            i += 1

        return marks

    def invalidate_cache(self, file_path: Optional[Path] = None) -> None:
        """Invalidate status cache for a file or all files."""
        if file_path and self.repo_root:
            cache_key = str(file_path.relative_to(self.repo_root))
            self.status_cache.pop(cache_key, None)
        else:
            self.status_cache.clear()

    def refresh_repo_root(self) -> None:
        """Refresh repository root detection."""
        self._find_repo_root()
        self.status_cache.clear()