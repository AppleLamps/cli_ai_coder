#!/usr/bin/env python3
"""Generate CLI documentation from help output."""

import subprocess
import sys
from pathlib import Path

def run_command(cmd):
    """Run a command and return its output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running command '{cmd}': {e}")
        return f"Error: {e}"

def generate_cli_docs():
    """Generate CLI documentation."""
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    docs_dir = project_dir / "docs"

    # Generate main help
    print("Generating main CLI help...")
    main_help = run_command(f"cd {project_dir} && python main.py --help")

    # Generate codemod help (placeholder for now)
    print("Generating codemod help...")
    codemod_help = """Usage: cli-ai-coder codemod [OPTIONS]

Run codemod transformations on your codebase.

Options:
  --transform TEXT          Codemod transform to apply (rename_symbol,
                           convert_print_to_logging, add_type_hints,
                           rename_export, remove_console, organize_imports)
  --old-name TEXT           Original name for rename operations
  --new-name TEXT           New name for rename operations
  --files TEXT              Glob pattern for files to transform
  --scope [current|changed|glob|all]
                           Scope of files to transform
  --preview-only            Show changes without applying them
  --interactive             Confirm each file before applying
  --max-files INTEGER       Maximum number of files to process
  --help                    Show this message and exit.

Examples:
  cli-ai-coder codemod --transform rename_symbol --old-name old_func --new-name new_func --files "*.py"
  cli-ai-coder codemod --transform convert_print_to_logging --scope changed
  cli-ai-coder codemod --transform remove_console --files "src/**/*.{js,ts}" --interactive"""

    # Create CLI commands page
    cli_commands_content = f"""# CLI Commands

This page contains the complete CLI reference for CLI AI Coder.

## Main Command

```bash
{main_help}
```

## Codemod Command

```bash
{codemod_help}
```

## Available Codemod Transforms

Run `cli-ai-coder codemod --list-transforms` to see all available transforms.

## Examples

### Basic Usage

```bash
# Get help
cli-ai-coder --help

# Start interactive mode
cli-ai-coder

# Run a codemod
cli-ai-coder codemod --transform rename_symbol --old-name old_func --new-name new_func
```

### Advanced Usage

```bash
# Preview codemod changes
cli-ai-coder codemod --transform convert_print_to_logging --preview-only

# Run on specific files
cli-ai-coder codemod --transform add_type_hints --files "src/**/*.py"

# Interactive mode
cli-ai-coder codemod --transform remove_console --interactive
```
"""

    # Write the CLI commands file
    cli_commands_path = docs_dir / "cli" / "commands.md"
    cli_commands_path.parent.mkdir(exist_ok=True)
    with open(cli_commands_path, 'w') as f:
        f.write(cli_commands_content)

    print(f"Generated CLI documentation at {cli_commands_path}")

if __name__ == "__main__":
    generate_cli_docs()