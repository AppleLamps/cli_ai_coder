# CLI AI Coder

[![PyPI version](https://badge.fury.io/py/cli-ai-coder.svg)](https://pypi.org/project/cli-ai-coder/)
[![Homebrew](https://img.shields.io/badge/dynamic/json?url=https://formulae.brew.sh/api/formula/cli-ai-coder.json&query=$.versions.stable&label=homebrew)](https://formulae.brew.sh/formula/cli-ai-coder)

A terminal-native AI coding assistant built with Python and xAI's models.

## Installation

### PyPI (Recommended)

```bash
pipx install cli-ai-coder
```

Or with pip:

```bash
pip install cli-ai-coder
```

### Homebrew (macOS/Linux)

```bash
brew install cli-ai-coder
```

### From Source

```bash
git clone https://github.com/yourusername/cli-ai-coder.git
cd cli-ai-coder
pip install -e .
```

## Setup

Set your xAI API key:

```bash
export XAI_API_KEY="your-api-key-here"
```

For other providers, see configuration below.

## Usage

Launch the editor:

```bash
ccode open [path]
```

Other commands:

```bash
ccode doctor          # Check environment and providers
ccode plan            # Run planner
ccode pipeline        # Run pipeline
ccode index --rebuild # Rebuild code index
```

### Keybindings

- **Alt+A**: AI panel
- **Alt-D**: Diagnostics
- **Alt-G**: Git panel
- **Alt-P**: Planner
- **Alt-W**: Playground
- **Alt-O**: Organize imports
- **Alt-.**: LSP Quick Fix
- **Tab**: Accept inline suggestion
- **Alt-]**: Next inline suggestion
- **Esc**: Dismiss inline suggestion

### Configuration

Create `~/.cli_ai_coder.toml`:

```toml
[ai]
provider = "xai"  # or "openai", "ollama"

[billing]
monthly_budget_usd = 5.0
soft_limit_ratio = 0.8
hard_stop = false

[inline_suggest]
enabled = true
idle_ms = 800
max_chars = 120
model = "grok-code-fast-1"
```

## Budget Commands

- `:budget` - Show current budget status
- `:budget-set 10` - Set monthly budget to $10
- `:budget-reset` - Reset budget for current month
- `:budget-export` - Export budget history to CSV

## Development

Run tests:

```bash
pytest
```

Build package:

```bash
python -m build
```
