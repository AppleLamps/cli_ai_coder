"""JavaScript/TypeScript codemods using regex patterns."""

import re
from typing import List, Tuple
from .base import BaseCodeMod


class RenameExportCodemod(BaseCodeMod):
    """Rename an export symbol."""

    def __init__(self, old_name: str, new_name: str):
        super().__init__(
            name="rename_export",
            description=f"Rename export '{old_name}' to '{new_name}'"
        )
        self.old_name = old_name
        self.new_name = new_name

    def preview(self, path: str, text: str) -> str:
        modified = self.apply(path, text)
        return self._create_unified_diff(path, text, modified)

    def apply(self, path: str, text: str) -> str:
        # Pattern for named exports: export { old_name } or export { old_name as alias }
        patterns = [
            (r'\bexport\s*\{\s*' + re.escape(self.old_name) + r'\s*\}', f'export {{ {self.new_name} }}'),
            (r'\bexport\s*\{\s*' + re.escape(self.old_name) + r'\s+as\s+(\w+)\s*\}', f'export {{ {self.new_name} as \\1 }}'),
            # Also handle default exports
            (r'\bexport\s+default\s+' + re.escape(self.old_name), f'export default {self.new_name}'),
        ]

        result = text
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result)

        return result


class RemoveConsoleCodemod(BaseCodeMod):
    """Remove console.log, console.warn, etc. statements."""

    def __init__(self):
        super().__init__(
            name="remove_console",
            description="Remove all console.* calls"
        )

    def preview(self, path: str, text: str) -> str:
        modified = self.apply(path, text)
        return self._create_unified_diff(path, text, modified)

    def apply(self, path: str, text: str) -> str:
        # Remove console statements, handling various formats
        # This is a simple regex approach - not perfect but covers common cases
        patterns = [
            r'^\s*console\.\w+\([^;]*\);\s*$',  # console.log(...);
            r'^\s*console\.\w+\([^}]*\);\s*$',  # console.log(...); with possible }
            r'^\s*console\.\w+\([^)]*\)\s*$',   # console.log(...) without semicolon
        ]

        lines = text.splitlines()
        new_lines = []

        for line in lines:
            should_remove = False
            for pattern in patterns:
                if re.search(pattern, line.strip()):
                    should_remove = True
                    break
            if not should_remove:
                new_lines.append(line)

        return '\n'.join(new_lines)


class OrganizeImportsBestEffortCodemod(BaseCodeMod):
    """Attempt to organize imports (very basic)."""

    def __init__(self):
        super().__init__(
            name="organize_imports_best_effort",
            description="Basic import organization (experimental)"
        )

    def preview(self, path: str, text: str) -> str:
        modified = self.apply(path, text)
        return self._create_unified_diff(path, text, modified)

    def apply(self, path: str, text: str) -> str:
        # Very basic import organization
        # This is a placeholder - real import organization would need proper AST parsing
        lines = text.splitlines()
        import_lines = []
        other_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('export '):
                import_lines.append(line)
            else:
                other_lines.append(line)

        # Simple sort of import lines
        import_lines.sort()

        return '\n'.join(import_lines + [''] + other_lines)