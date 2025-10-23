# CLI Commands

This page contains the complete CLI reference for CLI AI Coder.

## Main Command

```bash
usage: main.py [-h] [--model MODEL] [--temp TEMP] [--max-input MAX_INPUT]
               [--no-metrics] [--read-only] [--offline]

AI Coder CLI

options:
  -h, --help            show this help message and exit
  --model MODEL         Override default model
  --temp TEMP           Override temperature
  --max-input MAX_INPUT
                        Override max input tokens
  --no-metrics          Disable metrics display
  --read-only           Read-only mode (no writes)
  --offline             Offline mode (no AI calls)

```

## Codemod Command

```bash
Usage: cli-ai-coder codemod [OPTIONS]

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
  cli-ai-coder codemod --transform remove_console --files "src/**/*.{js,ts}" --interactive
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
