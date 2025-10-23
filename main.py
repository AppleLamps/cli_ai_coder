"""CLI entrypoint for the AI Coder."""

import argparse
import sys
from editor.app import create_app


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="AI Coder CLI")
    parser.add_argument("--model", help="Override default model")
    parser.add_argument("--temp", type=float, help="Override temperature")
    parser.add_argument("--max-input", type=int, help="Override max input tokens")
    parser.add_argument("--no-metrics", action="store_true", help="Disable metrics display")
    parser.add_argument("--read-only", action="store_true", help="Read-only mode (no writes)")
    parser.add_argument("--offline", action="store_true", help="Offline mode (no AI calls)")

    args = parser.parse_args()

    # For now, just validate args exist - full implementation would require
    # passing these to the config/client
    if len(sys.argv) > 1 and not any(arg.startswith('-') for arg in sys.argv[1:]):
        print("Usage: python main.py [options]")
        print("Options:")
        print("  --model MODEL        Override default model")
        print("  --temp TEMP          Override temperature")
        print("  --max-input TOKENS   Override max input tokens")
        print("  --no-metrics         Disable metrics display")
        print("  --read-only          Read-only mode (no writes)")
        print("  --offline            Offline mode (no AI calls)")
        sys.exit(1)

    app = create_app()
    app.run()


if __name__ == "__main__":
    main()