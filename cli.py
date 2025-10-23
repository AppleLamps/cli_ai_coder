"""CLI entrypoint for CLI AI Coder using Typer."""

import typer
from pathlib import Path
from editor.app import create_app
from core.config import get_config
import os

app = typer.Typer()


@app.callback()
def callback():
    """CLI AI Coder - AI-powered code editing in the terminal."""


@app.command()
def open(path: str = typer.Argument(None, help="Path to open (defaults to current directory)")):
    """Open the AI coder interface."""
    if path:
        os.chdir(path)
    app = create_app()
    app.run()


@app.command()
def plan(playground: bool = typer.Option(False, "--playground", help="Use playground mode")):
    """Run the planner to create a plan for changes."""
    typer.echo("Plan command - not yet implemented")


@app.command()
def pipeline():
    """Run the pipeline for automated tasks."""
    typer.echo("Pipeline command - not yet implemented")


@app.command()
def index(rebuild: bool = typer.Option(False, "--rebuild", help="Rebuild the index")):
    """Manage the code index."""
    typer.echo(f"Index command - rebuild: {rebuild}")


@app.command()
def doctor():
    """Diagnose environment and provider setup."""
    config = get_config()

    typer.echo("🔍 CLI AI Coder Doctor")
    typer.echo("======================")

    # Check API keys
    api_key_envs = ["XAI_API_KEY", "OPENAI_API_KEY"]
    available_providers = []
    for env in api_key_envs:
        if os.getenv(env):
            provider = "xAI" if env == "XAI_API_KEY" else "OpenAI"
            available_providers.append(provider)
            typer.echo(f"✅ {provider} API key found")
        else:
            provider = "xAI" if env == "XAI_API_KEY" else "OpenAI"
            typer.echo(f"❌ {provider} API key missing")

    # Check Ollama (stub)
    typer.echo("⚠️  Ollama check not implemented yet")

    # Check config
    config_path = Path.home() / ".cli_ai_coder.toml"
    if config_path.exists():
        typer.echo(f"✅ Config file found at {config_path}")
    else:
        typer.echo(f"⚠️  Config file not found at {config_path} (using defaults)")

    # Check Python LSP
    import shutil
    if shutil.which(config.lsp_python_cmd):
        typer.echo(f"✅ LSP server '{config.lsp_python_cmd}' found")
    else:
        typer.echo(f"❌ LSP server '{config.lsp_python_cmd}' not found")

    if available_providers:
        typer.echo(f"\nAvailable providers: {', '.join(available_providers)}")
    else:
        typer.echo("\n❌ No providers available - set API keys")


if __name__ == "__main__":
    app()