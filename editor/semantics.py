"""Semantic token rendering for LSP."""

import time
from typing import Dict, List, Optional, Tuple
from prompt_toolkit.formatted_text import FormattedText


class SemanticTokenRenderer:
    """Renders semantic tokens with appropriate styles."""

    # Standard LSP semantic token types
    TOKEN_TYPES = [
        "namespace", "type", "class", "enum", "interface", "struct", "typeParameter",
        "parameter", "variable", "property", "enumMember", "event", "function",
        "method", "macro", "keyword", "modifier", "comment", "string", "number",
        "regexp", "operator"
    ]

    # Standard LSP semantic token modifiers
    TOKEN_MODIFIERS = [
        "declaration", "definition", "readonly", "static", "deprecated", "abstract",
        "async", "modification", "documentation", "defaultLibrary"
    ]

    def __init__(self):
        self.token_styles = self._get_token_styles()

    def _get_token_styles(self) -> Dict[str, str]:
        """Get style mapping for token types."""
        return {
            "namespace": "fg:#4EC9B0",  # Teal
            "type": "fg:#4EC9B0 bold",
            "class": "fg:#4EC9B0 bold",
            "enum": "fg:#4EC9B0",
            "interface": "fg:#4EC9B0",
            "struct": "fg:#4EC9B0",
            "typeParameter": "fg:#4EC9B0 italic",
            "parameter": "fg:#9CDCFE",
            "variable": "fg:#9CDCFE",
            "property": "fg:#9CDCFE",
            "enumMember": "fg:#4EC9B0",
            "event": "fg:#DCDCAA",
            "function": "fg:#DCDCAA",
            "method": "fg:#DCDCAA",
            "macro": "fg:#DCDCAA",
            "keyword": "fg:#569CD6 bold",
            "modifier": "fg:#569CD6",
            "comment": "fg:#6A9955 italic",
            "string": "fg:#CE9178",
            "number": "fg:#B5CEA8",
            "regexp": "fg:#D16969",
            "operator": "fg:#D4D4D4"
        }

    def render_tokens(self, text: str, tokens: List[Dict]) -> FormattedText:
        """Render text with semantic token highlighting."""
        if not tokens:
            return FormattedText([(self.token_styles.get("default", ""), text)])

        # Sort tokens by position
        sorted_tokens = sorted(tokens, key=lambda t: (t.get("line", 0), t.get("start", 0)))

        fragments = []
        lines = text.splitlines(keepends=True)
        current_line = 0
        current_char = 0

        for token in sorted_tokens:
            line = token.get("line", 0)
            start = token.get("start", 0)
            length = token.get("length", 0)
            token_type = token.get("type", "")
            modifiers = token.get("modifiers", [])

            # Skip to the token's line
            while current_line < line and current_line < len(lines):
                fragments.append(("", lines[current_line]))
                current_line += 1
                current_char = 0

            if current_line >= len(lines):
                break

            # Skip to the token's start position
            line_text = lines[current_line]
            if current_char < start:
                fragments.append(("", line_text[current_char:start]))
                current_char = start

            # Add the token with style
            if current_char < len(line_text):
                end_pos = min(current_char + length, len(line_text))
                token_text = line_text[current_char:end_pos]
                style = self._get_token_style(token_type, modifiers)
                fragments.append((style, token_text))
                current_char = end_pos

        # Add remaining text
        while current_line < len(lines):
            if current_char < len(lines[current_line]):
                fragments.append(("", lines[current_line][current_char:]))
            current_line += 1
            current_char = 0

        return FormattedText(fragments)

    def _get_token_style(self, token_type: str, modifiers: List[str]) -> str:
        """Get the style for a token type with modifiers."""
        base_style = self.token_styles.get(token_type, "")

        # Apply modifiers
        if "declaration" in modifiers or "definition" in modifiers:
            base_style += " underline"
        if "deprecated" in modifiers:
            base_style += " strikethrough"
        if "readonly" in modifiers:
            base_style += " dim"

        return base_style.strip()


class SemanticTokensManager:
    """Manages semantic tokens for files."""

    def __init__(self):
        self.renderer = SemanticTokenRenderer()
        self.tokens_cache: Dict[str, List[Dict]] = {}
        self.last_update: Dict[str, float] = {}

    def update_tokens(self, file_path: str, tokens: List[Dict]):
        """Update semantic tokens for a file."""
        self.tokens_cache[file_path] = tokens
        self.last_update[file_path] = time.time()

    def get_rendered_text(self, file_path: str, text: str) -> FormattedText:
        """Get rendered text with semantic highlighting."""
        tokens = self.tokens_cache.get(file_path, [])
        return self.renderer.render_tokens(text, tokens)

    def clear_cache(self, file_path: Optional[str] = None):
        """Clear token cache."""
        if file_path:
            self.tokens_cache.pop(file_path, None)
            self.last_update.pop(file_path, None)
        else:
            self.tokens_cache.clear()
            self.last_update.clear()