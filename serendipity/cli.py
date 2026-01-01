#!/usr/bin/env python3
"""serendipity - Personal Serendipity Engine CLI."""

import asyncio
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from serendipity.agent import Recommendation, SerendipityAgent
from serendipity.config.types import TypesConfig, context_from_storage
from serendipity.context_sources import ContextSourceManager
from serendipity.prompts.builder import PromptBuilder
from serendipity.resources import (
    get_base_template,
    get_default_style,
    get_discovery_prompt,
    get_frontend_design,
    get_system_prompt,
)

from serendipity.storage import HistoryEntry, ProfileManager, StorageManager

app = typer.Typer(
    name="serendipity",
    help="Personal Serendipity Engine - discover convergent and divergent content recommendations",
    add_completion=True,
    no_args_is_help=False,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)

# Profile subcommand group for managing what Claude knows about you
profile_app = typer.Typer(
    name="profile",
    help="View and manage your profile (what Claude knows about you)",
    rich_markup_mode="rich",
    invoke_without_command=True,
)
app.add_typer(profile_app, name="profile")

# Settings subcommand group
settings_app = typer.Typer(
    name="settings",
    help="Manage all serendipity settings (approaches, media types, context sources)",
    rich_markup_mode="rich",
    invoke_without_command=True,
)
app.add_typer(settings_app, name="settings")

console = Console()


@app.callback()
def callback(ctx: typer.Context) -> None:
    """Personal Serendipity Engine - discover convergent and divergent content recommendations."""
    # If no subcommand was invoked, run discover with defaults ("surprise me" mode)
    if ctx.invoked_subcommand is None:
        # Call discover_cmd directly with default values
        discover_cmd(
            file_path=None,
            paste=False,
            interactive=False,
            model=None,
            output_format="html",
            verbose=False,
            enable_source=None,
            disable_source=None,
            thinking=None,
        )


@profile_app.callback()
def profile_callback(
    ctx: typer.Context,
    show: bool = typer.Option(
        False,
        "--show",
        "-s",
        help="Show full content of all enabled sources",
    ),
    edit: bool = typer.Option(
        False,
        "--edit",
        "-e",
        help="Open taste.md in $EDITOR",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Interactive profile setup wizard",
    ),
    enable_source: Optional[str] = typer.Option(
        None,
        "--enable-source",
        help="Enable a context source",
    ),
    disable_source: Optional[str] = typer.Option(
        None,
        "--disable-source",
        help="Disable a context source",
    ),
) -> None:
    """View your profile - what Claude knows about you.

    Shows all enabled context sources: taste, learnings, history, etc.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile             [dim]# Overview of all sources[/dim]
      [dim]$[/dim] serendipity profile --show      [dim]# Full content of each source[/dim]
      [dim]$[/dim] serendipity profile --edit      [dim]# Edit taste.md[/dim]
      [dim]$[/dim] serendipity profile -i          [dim]# Interactive setup wizard[/dim]
      [dim]$[/dim] serendipity profile --enable-source whorl
    """
    import yaml

    storage = StorageManager()
    storage.ensure_dirs()

    # Handle --enable-source / --disable-source
    if enable_source or disable_source:
        config = storage.load_config()
        source_name = enable_source or disable_source

        if source_name not in config.context_sources:
            console.print(f"[red]Error:[/red] Unknown source '{source_name}'")
            console.print(f"[dim]Available: {', '.join(config.context_sources.keys())}[/dim]")
            raise typer.Exit(1)

        yaml_content = storage.settings_path.read_text()
        data = yaml.safe_load(yaml_content) or {}
        if "context_sources" not in data:
            data["context_sources"] = {}
        if source_name not in data["context_sources"]:
            data["context_sources"][source_name] = config.context_sources[source_name].raw_config.copy()
        data["context_sources"][source_name]["enabled"] = bool(enable_source)
        storage.settings_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

        action = "Enabled" if enable_source else "Disabled"
        console.print(f"[green]{action} '{source_name}'[/green]")
        return

    # Handle -i interactive wizard
    if interactive:
        _profile_interactive_wizard(storage)
        return

    # Handle --edit flag
    if edit:
        taste_path = storage.taste_path
        if not taste_path.exists():
            taste_path.parent.mkdir(parents=True, exist_ok=True)
            taste_path.write_text(
                "# My Taste Profile\n\n"
                "<!-- DELETE EVERYTHING AND REPLACE WITH YOUR TASTE -->\n\n"
                "Describe your aesthetic preferences, interests, and what you enjoy.\n\n"
                "Examples:\n"
                "- I'm drawn to Japanese minimalism and wabi-sabi aesthetics\n"
                "- I love long-form essays on philosophy and design\n"
                "- I appreciate things that feel contemplative and unhurried\n"
            )
        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(taste_path)])
        console.print(success(f"Taste profile saved to {taste_path}"))
        return

    # If subcommand provided, let it handle
    if ctx.invoked_subcommand is not None:
        return

    # Run migration if needed
    migrations = storage.migrate_if_needed()
    for msg in migrations:
        console.print(f"[yellow]{msg}[/yellow]")

    # Load settings to get context sources
    settings = storage.load_config()

    console.print("\n[bold]Your Profile[/bold]")
    console.print("[dim]What Claude knows about you (enabled context sources)[/dim]\n")

    total_words = 0

    for name, source_config in settings.context_sources.items():
        status = "[green]●[/green]" if source_config.enabled else "[dim]○[/dim]"
        source_type = f"[dim]{source_config.type}[/dim]"

        if source_config.enabled:
            # Show content for enabled sources
            content = ""
            words = 0

            if source_config.type == "loader":
                # Load content from loader
                if name == "taste":
                    content = storage.load_taste()
                    if "Describe your aesthetic preferences" in content:
                        content = ""  # Skip default template
                elif name == "learnings":
                    content = storage.load_learnings()
                elif name == "history":
                    recent = storage.load_recent_history(20)
                    content = f"{len(recent)} recent items"
                elif name == "style_guidance":
                    content = "[custom HTML styling]"

            if content:
                words = storage.count_words(content) if name != "history" else 0
                total_words += words

            if show and content and name not in ["history", "style_guidance"]:
                # Full content mode
                console.print(f"{status} [bold]{name}[/bold] ({source_type}) - {words} words")
                console.print(Panel(content, border_style="dim"))
            else:
                # Summary mode
                if content:
                    preview = content[:100].replace('\n', ' ')
                    if len(content) > 100:
                        preview += "..."
                    console.print(f"{status} [bold]{name}[/bold] ({source_type})")
                    console.print(f"   [dim]{preview}[/dim]")
                else:
                    console.print(f"{status} [bold]{name}[/bold] ({source_type}) [dim]- empty[/dim]")
        else:
            console.print(f"{status} [dim]{name}[/dim] ({source_type}) - disabled")

    console.print(f"\n[dim]Total context: ~{total_words} words[/dim]")
    console.print(f"\n[dim]Setup wizard: serendipity profile -i[/dim]")
    console.print(f"[dim]Edit taste: serendipity profile --edit[/dim]")
    console.print(f"[dim]Toggle source: serendipity profile --enable-source <name>[/dim]")


def _profile_interactive_wizard(storage: StorageManager) -> None:
    """Interactive wizard for profile setup."""
    import yaml

    console.print(Panel(
        "Set up your profile - what Claude will know about you",
        title="Profile Setup Wizard",
        border_style="blue",
    ))

    # Step 1: Taste profile
    console.print("\n[bold]Step 1: Taste Profile[/bold]")
    taste_content = storage.load_taste()
    has_taste = taste_content.strip() and "Describe your aesthetic preferences" not in taste_content

    if has_taste:
        preview = taste_content[:200].replace('\n', ' ')
        if len(taste_content) > 200:
            preview += "..."
        console.print(f"[green]You have a taste profile:[/green] {preview}")
        edit_taste = questionary.confirm("Edit your taste profile?", default=False).ask()
    else:
        console.print("[yellow]No taste profile yet.[/yellow]")
        edit_taste = questionary.confirm("Create a taste profile now?", default=True).ask()

    if edit_taste:
        taste_path = storage.taste_path
        if not taste_path.exists():
            taste_path.parent.mkdir(parents=True, exist_ok=True)
            taste_path.write_text(
                "# My Taste Profile\n\n"
                "Describe your aesthetic preferences, interests, and what you enjoy.\n\n"
                "Examples:\n"
                "- I'm drawn to Japanese minimalism and wabi-sabi aesthetics\n"
                "- I love long-form essays on philosophy and design\n"
                "- I appreciate things that feel contemplative and unhurried\n"
            )
        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(taste_path)])
        console.print(success("Taste profile saved"))

    # Step 2: Context sources
    console.print("\n[bold]Step 2: Context Sources[/bold]")
    console.print("[dim]Choose which sources Claude uses to understand you[/dim]\n")

    config = storage.load_config()

    source_choices = []
    for name, source in config.context_sources.items():
        desc = source.description or f"{source.type} source"
        label = f"{name}: {desc}"
        source_choices.append(questionary.Choice(label, value=name, checked=source.enabled))

    selected = questionary.checkbox(
        "Enable sources (space to toggle):",
        choices=source_choices,
    ).ask()

    if selected is not None:
        # Update settings.yaml
        yaml_content = storage.settings_path.read_text()
        data = yaml.safe_load(yaml_content) or {}
        if "context_sources" not in data:
            data["context_sources"] = {}

        for name in config.context_sources.keys():
            if name not in data["context_sources"]:
                data["context_sources"][name] = config.context_sources[name].raw_config.copy()
            data["context_sources"][name]["enabled"] = name in selected

        storage.settings_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        console.print(success(f"Enabled sources: {', '.join(selected) if selected else 'none'}"))

    console.print("\n[green]Profile setup complete![/green]")
    console.print("[dim]Run 'serendipity' to get recommendations[/dim]")


def _settings_interactive_wizard(storage: StorageManager) -> None:
    """Interactive wizard for settings configuration."""
    import yaml

    console.print(Panel(
        "Configure how serendipity works",
        title="Settings Wizard",
        border_style="blue",
    ))

    config = storage.load_config()
    yaml_content = storage.settings_path.read_text()
    data = yaml.safe_load(yaml_content) or {}

    # Step 1: Model
    console.print("\n[bold]Step 1: Model[/bold]")
    model_choices = [
        questionary.Choice("haiku - Fast and cheap", value="haiku"),
        questionary.Choice("sonnet - Balanced (recommended)", value="sonnet"),
        questionary.Choice("opus - Most capable", value="opus"),
    ]
    current_model = config.model
    console.print(f"[dim]Current: {current_model}[/dim]")

    model = questionary.select(
        "Which Claude model?",
        choices=model_choices,
        default=current_model,
    ).ask()

    if model:
        data["model"] = model

    # Step 2: Total count
    console.print("\n[bold]Step 2: Recommendation Count[/bold]")
    console.print(f"[dim]Current: {config.total_count}[/dim]")

    count_str = questionary.text(
        "How many recommendations per run?",
        default=str(config.total_count),
        validate=lambda x: x.isdigit() and int(x) > 0,
    ).ask()

    if count_str:
        data["total_count"] = int(count_str)

    # Step 3: Approaches
    console.print("\n[bold]Step 3: Discovery Approaches[/bold]")
    console.print("[dim]How should Claude find content for you?[/dim]\n")

    approach_choices = []
    for name, approach in config.approaches.items():
        label = f"{approach.display_name}"
        approach_choices.append(questionary.Choice(label, value=name, checked=approach.enabled))

    selected_approaches = questionary.checkbox(
        "Enable approaches (space to toggle):",
        choices=approach_choices,
    ).ask()

    if selected_approaches is not None:
        if "approaches" not in data:
            data["approaches"] = {}
        for name in config.approaches.keys():
            if name not in data["approaches"]:
                data["approaches"][name] = {}
            data["approaches"][name]["enabled"] = name in selected_approaches

    # Step 4: Media types
    console.print("\n[bold]Step 4: Media Types[/bold]")
    console.print("[dim]What formats of content do you want?[/dim]\n")

    media_choices = []
    for name, media in config.media.items():
        label = f"{media.display_name}"
        media_choices.append(questionary.Choice(label, value=name, checked=media.enabled))

    selected_media = questionary.checkbox(
        "Enable media types (space to toggle):",
        choices=media_choices,
    ).ask()

    if selected_media is not None:
        if "media" not in data:
            data["media"] = {}
        for name in config.media.keys():
            if name not in data["media"]:
                data["media"][name] = {}
            data["media"][name]["enabled"] = name in selected_media

    # Step 5: Context sources
    console.print("\n[bold]Step 5: Context Sources[/bold]")
    console.print("[dim]What should Claude know about you?[/dim]\n")

    source_choices = []
    for name, source in config.context_sources.items():
        desc = source.description or f"{source.type} source"
        label = f"{name}: {desc}"
        source_choices.append(questionary.Choice(label, value=name, checked=source.enabled))

    selected_sources = questionary.checkbox(
        "Enable sources (space to toggle):",
        choices=source_choices,
    ).ask()

    if selected_sources is not None:
        if "context_sources" not in data:
            data["context_sources"] = {}
        for name in config.context_sources.keys():
            if name not in data["context_sources"]:
                data["context_sources"][name] = config.context_sources[name].raw_config.copy()
            data["context_sources"][name]["enabled"] = name in selected_sources

    # Save
    storage.settings_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    console.print("\n[green]Settings saved![/green]")
    console.print(f"[dim]Config: {storage.settings_path}[/dim]")


# Rich formatting helpers
def info(text: str) -> str:
    return f"[cyan]{text}[/cyan]"


def error(text: str) -> str:
    return f"[red]{text}[/red]"


def success(text: str) -> str:
    return f"[green]{text}[/green]"


def warning(text: str) -> str:
    return f"[yellow]{text}[/yellow]"


# =============================================================================
# Helper functions for hierarchical access
# =============================================================================


def is_source_editable(source_config) -> tuple[bool, Optional[Path]]:
    """Check if a source has an editable file path.

    Returns:
        (is_editable, file_path) - file_path is None if not editable
    """
    from serendipity.config.types import ContextSourceConfig

    # MCP sources are never editable from profile
    if source_config.type != "loader":
        return False, None

    raw = source_config.raw_config
    loader = raw.get("loader", "")

    # Only file_loader sources with a path are editable
    if loader != "serendipity.context_sources.builtins.file_loader":
        return False, None

    path_str = raw.get("options", {}).get("path")
    if not path_str:
        return False, None

    return True, Path(path_str).expanduser()


def get_settings_value(settings: dict, path: str) -> tuple:
    """Get a value from settings by dotted path.

    Args:
        settings: Full settings dict
        path: Dotted path like "approaches.convergent" or "model"

    Returns:
        (value, found) - value is None if not found
    """
    if not path:
        return settings, True

    parts = path.split(".")
    current = settings

    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None, False

    return current, True


def set_settings_value(settings: dict, path: str, value) -> bool:
    """Set a value in settings by dotted path.

    Returns:
        True if successful, False if path doesn't exist
    """
    parts = path.split(".")
    current = settings

    for part in parts[:-1]:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False

    if parts[-1] in current:
        current[parts[-1]] = value
        return True
    return False


# =============================================================================
# Source handlers for profile get/edit
# =============================================================================


def _handle_profile_history(
    storage: StorageManager,
    liked: bool = False,
    disliked: bool = False,
    limit: int = 20,
    clear: bool = False,
) -> None:
    """Handle history source operations."""
    if clear:
        if typer.confirm("Are you sure you want to clear all history?"):
            storage.clear_history()
            console.print(success("History cleared"))
        return

    # Get entries based on filter
    if liked:
        entries = storage.get_liked_entries()[-limit:]
        title = "Liked Recommendations"
    elif disliked:
        entries = storage.get_disliked_entries()[-limit:]
        title = "Disliked Recommendations"
    else:
        entries = storage.load_recent_history(limit)
        title = "Recent Recommendations"

    if not entries:
        console.print("[dim]No history found.[/dim]")
        return

    table = Table(title=title, show_lines=True)
    table.add_column("Type", style="cyan", width=10)
    table.add_column("URL", style="blue", no_wrap=False)
    table.add_column("Feedback", style="green", width=10)

    for entry in entries:
        feedback_str = entry.feedback or "[dim]-[/dim]"
        if entry.feedback == "liked":
            feedback_str = "[green]👍[/green]"
        elif entry.feedback == "disliked":
            feedback_str = "[red]👎[/red]"
        table.add_row(entry.type, entry.url, feedback_str)

    console.print(table)
    console.print(f"\n[dim]History file: {storage.history_path}[/dim]")


def _handle_profile_learnings(
    storage: StorageManager,
    interactive: bool = False,
    clear: bool = False,
    edit: bool = False,
) -> None:
    """Handle learnings source operations."""
    if clear:
        if not typer.confirm("Clear all learnings? This cannot be undone."):
            console.print(warning("Cancelled"))
            return
        storage.clear_learnings()
        console.print(success("Learnings cleared"))
        return

    if edit:
        learnings_path = storage.learnings_path
        if not learnings_path.exists():
            learnings_path.write_text("# My Discovery Learnings\n\n## Likes\n\n## Dislikes\n")
        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(learnings_path)])
        console.print(success(f"Learnings saved to {learnings_path}"))
        return

    if interactive:
        _learnings_interactive_wizard(storage)
        return

    # Default: show learnings
    learnings_content = storage.load_learnings()
    if learnings_content.strip():
        console.print(Panel(learnings_content, title="Discovery Learnings", border_style="blue"))
    else:
        console.print("[dim]No learnings yet. Run 'serendipity profile get learnings -i' to extract from history.[/dim]")
    console.print(f"\n[dim]Learnings file: {storage.learnings_path}[/dim]")


def _handle_profile_file_source(
    storage: StorageManager,
    source_config,
    file_path: Path,
    clear: bool = False,
    edit: bool = False,
) -> None:
    """Handle file-based loader sources (taste, notes, etc.)."""
    if clear:
        if not typer.confirm(f"Clear {source_config.name}? This cannot be undone."):
            console.print(warning("Cancelled"))
            return
        if file_path.exists():
            file_path.unlink()
        console.print(success(f"{source_config.name} cleared"))
        return

    if edit:
        if not file_path.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"# {source_config.name.title()}\n\n")
        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(file_path)])
        console.print(success(f"{source_config.name} saved to {file_path}"))
        return

    # Default: show content
    if file_path.exists():
        content = file_path.read_text()
        if content.strip():
            console.print(Panel(content, title=source_config.name.title(), border_style="blue"))
        else:
            console.print(f"[dim]{source_config.name} is empty.[/dim]")
    else:
        console.print(f"[dim]{source_config.name} file not found: {file_path}[/dim]")
    console.print(f"\n[dim]File: {file_path}[/dim]")


def _handle_profile_mcp_source(source_config) -> None:
    """Handle MCP source display (read-only config/status)."""
    import yaml

    console.print(f"\n[bold]{source_config.name}[/bold] [dim](MCP source)[/dim]")
    console.print(f"[dim]Type: {source_config.type}[/dim]")

    if source_config.description:
        console.print(f"[dim]Description: {source_config.description}[/dim]")

    # Show server configuration
    raw = source_config.raw_config
    server = raw.get("server", {})
    if server:
        console.print(f"\n[cyan]Server:[/cyan]")
        console.print(f"  URL: {server.get('url', 'not configured')}")
        console.print(f"  Type: {server.get('type', 'http')}")

    # Show port config
    port_config = raw.get("port", {})
    if port_config:
        console.print(f"  Port: {port_config.get('default', 'auto')}")

    # Show allowed tools
    tools = raw.get("tools", {})
    allowed = tools.get("allowed", [])
    if allowed:
        console.print(f"\n[cyan]Allowed tools:[/cyan]")
        for tool in allowed[:5]:
            console.print(f"  • {tool}")
        if len(allowed) > 5:
            console.print(f"  ... and {len(allowed) - 5} more")

    console.print(f"\n[dim]Status: {'enabled' if source_config.enabled else 'disabled'}[/dim]")
    console.print("[dim]MCP sources are read-only from profile.[/dim]")


def _handle_profile_generic_loader(storage: StorageManager, source_config) -> None:
    """Handle generic loader sources (like style_guidance)."""
    console.print(f"\n[bold]{source_config.name}[/bold] [dim](loader)[/dim]")
    console.print(f"[dim]Type: {source_config.type}[/dim]")

    if source_config.description:
        console.print(f"[dim]Description: {source_config.description}[/dim]")

    raw = source_config.raw_config
    loader = raw.get("loader", "unknown")
    console.print(f"\n[cyan]Loader:[/cyan] {loader}")

    # Try to get content preview
    if source_config.name == "style_guidance":
        console.print("\n[dim]Content: Dynamic HTML styling guidance based on taste profile[/dim]")
    else:
        console.print(f"\n[dim]This source has no editable file.[/dim]")

    console.print(f"[dim]Status: {'enabled' if source_config.enabled else 'disabled'}[/dim]")


def _read_from_clipboard() -> str:
    """Read content from clipboard."""
    try:
        import pyperclip

        content = pyperclip.paste()
        if not content:
            console.print(error("Clipboard is empty"))
            raise typer.Exit(code=1)
        return content
    except ImportError:
        console.print(error("pyperclip not installed. Run: pip install pyperclip"))
        raise typer.Exit(code=1)


def _read_from_editor() -> str:
    """Open $EDITOR for user to compose context."""
    editor = os.environ.get("EDITOR", "vim")

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        delete=False,
        prefix="serendipity_context_",
    ) as f:
        # Start with empty file
        temp_path = Path(f.name)

    try:
        subprocess.run([editor, str(temp_path)], check=True)
        content = temp_path.read_text()

        # Check if user actually wrote something
        if not content.strip():
            console.print(error("No content written. Aborting."))
            raise typer.Exit(code=1)

        return content
    except subprocess.CalledProcessError:
        console.print(error(f"Editor {editor} exited with error"))
        raise typer.Exit(code=1)
    finally:
        temp_path.unlink(missing_ok=True)


def _read_from_stdin() -> Optional[str]:
    """Read content from stdin if piped."""
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return None


def _get_context(
    file_path: Optional[Path],
    paste: bool,
    interactive: bool,
) -> Optional[str]:
    """Get context from various sources using priority waterfall.

    Priority:
    1. Explicit file argument
    2. -p flag (clipboard)
    3. -i flag (editor)
    4. Stdin (if piped)
    5. None (surprise me mode)

    Returns:
        Context string or None if no input provided.
    """
    # 1. File argument
    if file_path is not None:
        if file_path == Path("-"):
            # Read from stdin explicitly
            content = sys.stdin.read()
            if not content.strip():
                console.print(error("No content from stdin"))
                raise typer.Exit(code=1)
            return content

        if not file_path.exists():
            console.print(error(f"File not found: {file_path}"))
            raise typer.Exit(code=1)
        return file_path.read_text()

    # 2. Clipboard
    if paste:
        return _read_from_clipboard()

    # 3. Interactive editor
    if interactive:
        return _read_from_editor()

    # 4. Stdin (if piped)
    stdin_content = _read_from_stdin()
    if stdin_content:
        return stdin_content

    # 5. No input - return None for "surprise me" mode
    return None


def _display_terminal(result) -> None:
    """Display results in terminal."""
    # Convergent table
    if result.convergent:
        table = Table(title="More Like This (Convergent)", show_lines=True)
        table.add_column("URL", style="cyan", no_wrap=False)
        table.add_column("Why", style="white")
        for r in result.convergent:
            table.add_row(r.url, r.reason)
        console.print(table)
        console.print()

    # Divergent table
    if result.divergent:
        table = Table(title="Expand Your Palette (Divergent)", show_lines=True)
        table.add_column("URL", style="yellow", no_wrap=False)
        table.add_column("Why", style="white")
        for r in result.divergent:
            table.add_row(r.url, r.reason)
        console.print(table)


def _save_to_history(
    storage: StorageManager,
    result,
) -> None:
    """Save discovery results to history."""
    entries = []
    timestamp = datetime.now().isoformat()

    for rec in result.convergent:
        entries.append(HistoryEntry(
            url=rec.url,
            reason=rec.reason,
            type="convergent",
            feedback=None,
            timestamp=timestamp,
            session_id=result.session_id,
        ))

    for rec in result.divergent:
        entries.append(HistoryEntry(
            url=rec.url,
            reason=rec.reason,
            type="divergent",
            feedback=None,
            timestamp=timestamp,
            session_id=result.session_id,
        ))

    storage.append_history(entries)


def _start_feedback_server(
    storage: StorageManager,
    agent: SerendipityAgent,
    port: int,
    html_content: Optional[str] = None,
    static_dir: Optional[Path] = None,
    user_input: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[threading.Thread, int]:
    """Start the feedback server in a background thread.

    Returns:
        Tuple of (thread, actual_port) where actual_port may differ from port if it was taken.
    """
    import queue

    from serendipity.server import FeedbackServer

    # Queue to communicate actual port back from thread
    port_queue: queue.Queue[int | Exception] = queue.Queue()

    # Store reference to server for registering session input
    server_ref = [None]

    async def on_more_request(session_id: str, rec_type: str, count: int, session_feedback: list = None):
        """Handle 'more' requests from HTML."""
        try:
            console.print(f"[dim]Getting {count} more {rec_type} recommendations...[/dim]")
            if session_feedback:
                console.print(f"[dim]With {len(session_feedback)} feedback items from this session[/dim]")
            recommendations = await agent.get_more(session_id, rec_type, count, session_feedback)

            # Save to history
            entries = []
            timestamp = datetime.now().isoformat()
            for rec in recommendations:
                entries.append(HistoryEntry(
                    url=rec.url,
                    reason=rec.reason,
                    type=rec_type,
                    feedback=None,
                    timestamp=timestamp,
                    session_id=session_id,
                ))
            storage.append_history(entries)

            return [{"url": r.url, "reason": r.reason} for r in recommendations]
        except Exception as e:
            import traceback
            console.print(f"[red]Error getting more recommendations: {e}[/red]")
            traceback.print_exc()
            raise

    async def run_server():
        server = FeedbackServer(
            storage=storage,
            on_more_request=on_more_request,
            idle_timeout=600,  # 10 minutes
            html_content=html_content,
            static_dir=static_dir,
        )
        server_ref[0] = server

        # Register user input for context panel
        if session_id and user_input:
            server.register_session_input(session_id, user_input)

        # Start server and get actual port (may differ if preferred was taken)
        actual_port = await server.start(port)
        port_queue.put(actual_port)

        # Keep running until interrupted
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            await server.stop()

    def thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_server())
        except KeyboardInterrupt:
            pass
        except Exception as e:
            import traceback
            port_queue.put(e)  # Signal error to main thread
            console.print(f"[red]Feedback server error: {e}[/red]")
            traceback.print_exc()

    thread = threading.Thread(target=thread_target, daemon=True)
    thread.start()

    # Wait for actual port from server thread
    import time
    try:
        result = port_queue.get(timeout=5.0)
        if isinstance(result, Exception):
            raise result
        actual_port = result
    except queue.Empty:
        console.print("[yellow]Warning: Feedback server may not be ready[/yellow]")
        actual_port = port  # Fall back to requested port

    # Verify server is responding on actual port
    import urllib.request
    for _ in range(10):  # Try for up to 1 second
        try:
            req = urllib.request.Request(f"http://localhost:{actual_port}/health")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)
    else:
        console.print("[yellow]Warning: Feedback server health check failed[/yellow]")

    return thread, actual_port


@app.command(name="discover")
def discover_cmd(
    file_path: Optional[Path] = typer.Argument(
        None,
        help="Path to context file (use '-' for stdin)",
    ),
    paste: bool = typer.Option(
        False,
        "--paste",
        "-p",
        help="Read context from clipboard",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Open $EDITOR to compose context",
    ),
    model: str = typer.Option(
        None,
        "--model",
        "-m",
        help="Claude model (haiku, sonnet, opus)",
    ),
    output_format: str = typer.Option(
        "html",
        "--output-format",
        "-o",
        help="Output format: html, terminal, json",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed progress",
    ),
    enable_source: Optional[list[str]] = typer.Option(
        None,
        "--enable-source",
        "-s",
        help="Enable a context source for this run (can repeat: -s whorl -s custom)",
    ),
    disable_source: Optional[list[str]] = typer.Option(
        None,
        "--disable-source",
        "-d",
        help="Disable a context source for this run (can repeat)",
    ),
    thinking: Optional[int] = typer.Option(
        None,
        "--thinking",
        "-t",
        help="Enable extended thinking with specified token budget (e.g., 10000)",
    ),
    count: Optional[int] = typer.Option(
        None,
        "--count",
        "-n",
        help="Number of recommendations to generate (default: 10)",
    ),
    port: Optional[int] = typer.Option(
        None,
        "--port",
        help="Port for feedback server (default: 9876)",
    ),
) -> None:
    """Discover convergent and divergent content recommendations.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity                           [dim]# Surprise me (uses profile)[/dim]
      [dim]$[/dim] serendipity "I'm in the mood for..."  [dim]# Quick prompt[/dim]
      [dim]$[/dim] serendipity notes.md                  [dim]# From file[/dim]
      [dim]$[/dim] serendipity -p                        [dim]# From clipboard[/dim]
      [dim]$[/dim] serendipity -i                        [dim]# Open editor[/dim]
      [dim]$[/dim] serendipity -o terminal               [dim]# No browser[/dim]
      [dim]$[/dim] serendipity -s whorl                  [dim]# With Whorl knowledge base[/dim]
      [dim]$[/dim] serendipity -d history                [dim]# Without history[/dim]
    """
    # Load storage
    storage = StorageManager()
    storage.ensure_dirs()

    # Run migration if needed
    migrations = storage.migrate_if_needed()
    for msg in migrations:
        console.print(f"[yellow]{msg}[/yellow]")

    # Load settings config
    settings = storage.load_config()

    # Use settings defaults if not specified (CLI flags override settings)
    if model is None:
        model = settings.model
    max_thinking_tokens = thinking if thinking is not None else settings.thinking_tokens
    total_count = count if count is not None else settings.total_count
    server_port = port if port is not None else settings.feedback_server_port

    # Get context from input sources
    context = _get_context(file_path, paste, interactive)

    # Handle "surprise me" mode (no input provided)
    if context is None:
        # Check if user has a customized taste profile
        taste = storage.load_taste()
        has_taste = taste.strip() and not (
            "Describe your aesthetic preferences" in taste and "Examples:" in taste
        )

        if not has_taste:
            # No profile - show onboarding
            console.print(Panel(
                "[bold]Welcome to Serendipity![/bold]\n\n"
                "To get personalized recommendations, first set up your taste profile:\n\n"
                "  serendipity profile taste --edit\n\n"
                "Or provide context for what you're looking for:\n\n"
                "  serendipity \"I'm in the mood for...\"    # Quick prompt\n"
                "  serendipity -i                          # Open editor\n"
                "  serendipity notes.md                    # From file\n",
                title="Getting Started",
                border_style="blue",
            ))
            raise typer.Exit(code=0)

        # Has profile - use "surprise me" mode
        context = (
            "Surprise me! Based on my taste profile and what I've liked before, "
            "recommend things you think I'll enjoy. No specific mood or topic - "
            "just your best guesses for what would delight me right now."
        )
        console.print("[dim]No input provided - running in 'surprise me' mode[/dim]")
        console.print()

    # Create context source manager using settings
    ctx_manager = ContextSourceManager(settings, console)

    # Build enable/disable lists from flags
    sources_to_enable = list(enable_source) if enable_source else []
    sources_to_disable = list(disable_source) if disable_source else []

    # Initialize sources and build context (async operations)
    async def init_and_build_context():
        # Initialize sources (checks setup, starts MCP servers)
        init_warnings = await ctx_manager.initialize(
            enable_sources=sources_to_enable,
            disable_sources=sources_to_disable,
        )
        # Build context from all enabled sources
        context_aug, load_warnings = await ctx_manager.build_context(storage)
        # Extract style_guidance (backwards compatibility)
        style_guide = ""
        if "style_guidance" in ctx_manager.sources and ctx_manager.sources["style_guidance"].enabled:
            style_result = await ctx_manager.sources["style_guidance"].load(storage)
            style_guide = style_result.prompt_section
        return init_warnings, context_aug, load_warnings, style_guide

    init_warnings, context_augmentation, load_warnings, style_guidance = asyncio.run(
        init_and_build_context()
    )
    for warn_msg in init_warnings:
        console.print(warning(warn_msg))
    for warn_msg in load_warnings:
        console.print(warning(warn_msg))

    # Check total context length
    total_context = context_augmentation + "\n\n" + context
    total_words = storage.count_words(total_context)
    if total_words > 10000:
        console.print(warning(
            f"Total context is {total_words:,} words (>10K). "
            f"This may impact quality or cost. Consider condensing."
        ))

    if verbose:
        enabled_sources = ctx_manager.get_enabled_source_names()
        console.print(Panel(
            f"Context length: {len(context)} chars\n"
            f"Model: {model}\n"
            f"Total count: {total_count}\n"
            f"Context sources: {', '.join(enabled_sources) if enabled_sources else 'none'}\n"
            f"MCP servers: {', '.join(ctx_manager.get_mcp_servers().keys()) or 'none'}\n"
            f"Thinking: {max_thinking_tokens if max_thinking_tokens else 'disabled'}",
            title="Configuration",
            border_style="blue",
        ))

    # Get template path (copies package default to user location on first use)
    template_path = storage.get_template_path(get_base_template())

    # Run discovery
    agent = SerendipityAgent(
        console=console,
        model=model,
        verbose=verbose,
        context_manager=ctx_manager,
        server_port=server_port,
        template_path=template_path,
        max_thinking_tokens=max_thinking_tokens,
        types_config=settings,
        storage=storage,
    )

    console.print("[bold green]Discovering...[/bold green]")
    console.print()
    result = agent.run_sync(
        context,
        context_augmentation=context_augmentation,
        style_guidance=style_guidance,
    )
    console.print()

    # Show session info (useful for debugging and resuming)
    if result.session_id:
        console.print(f"[dim]Session: {result.session_id}[/dim]")
        console.print(f"[dim]Resume: claude -r {result.session_id}[/dim]")
        console.print()

    # Save to history (unless history source is disabled)
    history_enabled = "history" not in sources_to_disable
    if history_enabled:
        _save_to_history(storage, result)

    # Output based on format
    if output_format == "html":
        # Require Claude to have written the HTML file
        if not result.html_path or not result.html_path.exists():
            console.print(error("Claude failed to write HTML file"))
            console.print(f"[dim]Expected path: {agent.output_dir}[/dim]")
            raise typer.Exit(code=1)

        # Start feedback server with static file serving
        _, actual_port = _start_feedback_server(
            storage,
            agent,
            server_port,
            static_dir=agent.output_dir,
            user_input=context,
            session_id=result.session_id,
        )

        # Open browser to the specific file (use actual port which may differ if preferred was taken)
        import webbrowser
        filename = result.html_path.name
        url = f"http://localhost:{actual_port}/{filename}"
        webbrowser.open(url)

        console.print(success(f"Opened in browser: {url}"))
        console.print(f"[dim]HTML file: {result.html_path}[/dim]")
        if actual_port != server_port:
            console.print(f"[yellow]Port {server_port} was in use, using port {actual_port}[/yellow]")
        console.print(f"[dim]Feedback server running on localhost:{actual_port}[/dim]")
        console.print("[dim]Press Ctrl+C to stop the server when done.[/dim]")

        # Keep main thread alive for feedback server
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[dim]Server stopped.[/dim]")

    elif output_format == "terminal":
        _display_terminal(result)
    elif output_format == "json":
        import json

        output = {
            "convergent": [{"url": r.url, "reason": r.reason} for r in result.convergent],
            "divergent": [{"url": r.url, "reason": r.reason} for r in result.divergent],
        }
        console.print_json(json.dumps(output, indent=2))
    else:
        console.print(error(f"Unknown output format: {output_format}"))
        raise typer.Exit(code=1)

    # Show cost (for non-HTML output)
    if output_format != "html":
        if result.cost_usd:
            console.print(f"[dim]Cost: ${result.cost_usd:.4f}[/dim]")


@settings_app.callback()
def settings_callback(
    ctx: typer.Context,
    show: bool = typer.Option(
        True,
        "--show",
        "-s",
        help="Show current settings",
    ),
    edit: bool = typer.Option(
        False,
        "--edit",
        "-e",
        help="Open settings.yaml in $EDITOR",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Interactive settings wizard",
    ),
    preview: bool = typer.Option(
        False,
        "--preview",
        "-p",
        help="Preview the prompt that would be generated",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        "-r",
        help="Reset settings.yaml to defaults",
    ),
    enable_source: Optional[str] = typer.Option(
        None,
        "--enable-source",
        help="Enable a context source by name",
    ),
    disable_source: Optional[str] = typer.Option(
        None,
        "--disable-source",
        help="Disable a context source by name",
    ),
) -> None:
    """Manage all serendipity settings.

    Single configuration file for approaches, media types, context sources,
    and runtime settings (model, total_count, feedback_server_port).

    EXAMPLES:
    $ serendipity settings                        # Show all settings
    $ serendipity settings -i                     # Interactive wizard
    $ serendipity settings --edit                 # Edit in $EDITOR
    $ serendipity settings --reset                # Restore defaults
    $ serendipity settings --enable-source whorl  # Enable context source
    $ serendipity settings add media -i           # Add new media type
    """
    # If a subcommand is invoked, skip the callback logic
    if ctx.invoked_subcommand is not None:
        return
    import yaml

    console = Console()
    storage = StorageManager()
    settings_path = storage.settings_path

    if reset:
        # Confirm before overwriting
        if settings_path.exists():
            console.print(f"[yellow]This will overwrite {settings_path}[/yellow]")
            if not typer.confirm("Reset to defaults?", default=False):
                console.print("[dim]Cancelled.[/dim]")
                return
        TypesConfig.reset(settings_path)
        console.print(f"[green]Reset settings.yaml to defaults.[/green]")
        console.print(f"[dim]{settings_path}[/dim]")
        return

    if edit:
        # Open in editor (auto-creates if missing via from_yaml)
        editor = os.environ.get("EDITOR", "vim")
        TypesConfig.from_yaml(settings_path)  # Ensure file exists
        subprocess.run([editor, str(settings_path)])
        return

    if interactive:
        _settings_interactive_wizard(storage)
        return

    if preview:
        # Show the prompt that would be generated
        config = storage.load_config()
        builder = PromptBuilder(config)
        console.print(Panel(
            builder.build_type_guidance(),
            title="Generated Prompt Sections",
            border_style="dim",
        ))
        return

    # Handle enable/disable source
    if enable_source or disable_source:
        config = storage.load_config()

        if not settings_path.exists():
            TypesConfig.write_defaults(settings_path)

        yaml_content = settings_path.read_text()
        data = yaml.safe_load(yaml_content) or {}

        if "context_sources" not in data:
            data["context_sources"] = {}

        source_name = enable_source or disable_source
        if source_name not in config.context_sources:
            console.print(f"[red]Error:[/red] Unknown source '{source_name}'")
            console.print(f"[dim]Available sources: {', '.join(config.context_sources.keys())}[/dim]")
            raise typer.Exit(1)

        if source_name not in data["context_sources"]:
            source_config = config.context_sources[source_name]
            data["context_sources"][source_name] = source_config.raw_config.copy()

        data["context_sources"][source_name]["enabled"] = bool(enable_source)

        settings_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

        action = "Enabled" if enable_source else "Disabled"
        console.print(f"[green]{action} '{source_name}'[/green] in {settings_path}")
        return

    # Default: show settings
    config = storage.load_config()

    # Show top-level settings
    console.print("\n[bold]Settings[/bold]")
    console.print(f"  model: [cyan]{config.model}[/cyan]")
    console.print(f"  total_count: [cyan]{config.total_count}[/cyan]")
    console.print(f"  feedback_server_port: [cyan]{config.feedback_server_port}[/cyan]")
    thinking_display = f"[cyan]{config.thinking_tokens}[/cyan]" if config.thinking_tokens else "[dim]disabled[/dim]"
    console.print(f"  thinking_tokens: {thinking_display}")

    # Show approaches
    console.print("\n[bold]Approaches[/bold] (how to find):")
    for approach in config.approaches.values():
        status = "[green]enabled[/green]" if approach.enabled else "[dim]disabled[/dim]"
        console.print(f"  [cyan]{approach.name}[/cyan]: {approach.display_name} ({status})")

    # Show media types
    console.print("\n[bold]Media Types[/bold] (what format):")
    for media in config.media.values():
        status = "[green]enabled[/green]" if media.enabled else "[dim]disabled[/dim]"
        pref = f' - "{media.preference}"' if media.preference else ""
        console.print(f"  [green]{media.name}[/green]: {media.display_name} ({status}){pref}")

    console.print(f"\n[dim]Agent chooses distribution based on your taste.md[/dim]")

    # Show context sources
    if config.context_sources:
        console.print("\n[bold]Context Sources[/bold] (user profile):")
        for name, source in config.context_sources.items():
            status = "[green]enabled[/green]" if source.enabled else "[dim]disabled[/dim]"
            source_type = f"[dim]{source.type}[/dim]"
            desc = f" - {source.description}" if source.description else ""
            console.print(f"  [yellow]{name}[/yellow]: {status} ({source_type}){desc}")

    # Show prompts status
    console.print("\n[bold]Prompts[/bold] (agent instructions):")
    prompt_files = {
        "discovery": ("discovery.txt", get_discovery_prompt),
        "frontend_design": ("frontend_design.txt", get_frontend_design),
        "system": ("system.txt", get_system_prompt),
    }
    for name, (filename, default_getter) in prompt_files.items():
        prompt_path = storage.prompts_dir / filename
        if prompt_path.exists():
            is_custom = prompt_path.read_text() != default_getter()
            status = "[yellow]custom[/yellow]" if is_custom else "[dim]default[/dim]"
        else:
            status = "[dim]default[/dim]"
        console.print(f"  [cyan]{name}[/cyan]: {status}")

    # Show stylesheet status
    default_css = get_default_style()
    if storage.style_path.exists():
        is_custom = storage.style_path.read_text() != default_css
        style_status = "[yellow]custom[/yellow]" if is_custom else "[dim]default[/dim]"
    else:
        style_status = "[dim]default[/dim]"
    console.print(f"\n[bold]Stylesheet[/bold]: {style_status}")

    if settings_path.exists():
        console.print(f"\n[dim]Config: {settings_path}[/dim]")
        console.print(f"[dim]Prompts: {storage.prompts_dir}[/dim]")
        console.print(f"[dim]Style: {storage.style_path}[/dim]")
    else:
        console.print(f"\n[dim]Using defaults. Run 'serendipity settings --edit' to customize.[/dim]")


# =============================================================================
# New hierarchical settings get/edit commands
# =============================================================================


@settings_app.command("get")
def settings_get_cmd(
    path: Optional[str] = typer.Argument(None, help="Dotted path (e.g., approaches.convergent, media.youtube)"),
) -> None:
    """Show settings value(s) by path.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity settings get                       [dim]# All settings[/dim]
      [dim]$[/dim] serendipity settings get model                  [dim]# Just model[/dim]
      [dim]$[/dim] serendipity settings get approaches             [dim]# Approaches section[/dim]
      [dim]$[/dim] serendipity settings get approaches.convergent  [dim]# One approach[/dim]
      [dim]$[/dim] serendipity settings get media.youtube          [dim]# YouTube config[/dim]
      [dim]$[/dim] serendipity settings get context_sources.whorl  [dim]# Whorl source[/dim]
    """
    import yaml

    storage = StorageManager()
    settings_path = storage.settings_path

    if not settings_path.exists():
        console.print("[dim]No settings file yet. Using defaults.[/dim]")
        TypesConfig.from_yaml(settings_path)  # Create default

    settings_data = yaml.safe_load(settings_path.read_text()) or {}

    if path is None:
        # Show all - just dump the full YAML
        console.print(Panel(
            yaml.dump(settings_data, default_flow_style=False, sort_keys=False),
            title="settings.yaml",
            border_style="blue",
        ))
        console.print(f"\n[dim]File: {settings_path}[/dim]")
        return

    value, found = get_settings_value(settings_data, path)
    if not found:
        console.print(error(f"Path not found: {path}"))
        # Suggest valid top-level keys
        top_keys = list(settings_data.keys())
        console.print(f"[dim]Available top-level keys: {', '.join(top_keys)}[/dim]")
        raise typer.Exit(1)

    # Display based on type
    if isinstance(value, dict):
        console.print(Panel(
            yaml.dump(value, default_flow_style=False, sort_keys=False),
            title=path,
            border_style="blue",
        ))
    elif isinstance(value, list):
        console.print(Panel(
            yaml.dump(value, default_flow_style=False),
            title=path,
            border_style="blue",
        ))
    else:
        console.print(f"[cyan]{path}[/cyan]: {value}")


@settings_app.command("edit")
def settings_edit_cmd(
    path: Optional[str] = typer.Argument(None, help="Dotted path to edit (e.g., media.youtube)"),
) -> None:
    """Edit settings in $EDITOR.

    If path is given, opens editor with just that section.
    Changes are merged back into settings.yaml.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity settings edit                       [dim]# Edit whole file[/dim]
      [dim]$[/dim] serendipity settings edit approaches            [dim]# Edit approaches section[/dim]
      [dim]$[/dim] serendipity settings edit media.youtube         [dim]# Edit youtube config[/dim]
      [dim]$[/dim] serendipity settings edit context_sources.whorl [dim]# Edit whorl config[/dim]
    """
    import yaml

    storage = StorageManager()
    settings_path = storage.settings_path

    # Ensure file exists
    if not settings_path.exists():
        TypesConfig.from_yaml(settings_path)

    if path is None:
        # Edit whole file (existing behavior)
        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(settings_path)])
        console.print(success(f"Settings saved to {settings_path}"))
        return

    # Edit subset
    settings_data = yaml.safe_load(settings_path.read_text()) or {}
    value, found = get_settings_value(settings_data, path)

    if not found:
        console.print(error(f"Path not found: {path}"))
        top_keys = list(settings_data.keys())
        console.print(f"[dim]Available top-level keys: {', '.join(top_keys)}[/dim]")
        raise typer.Exit(1)

    # Write subset to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(f"# Editing: {path}\n")
        f.write(f"# Save and close to apply changes\n\n")
        f.write(yaml.dump(value, default_flow_style=False, sort_keys=False))
        temp_path = Path(f.name)

    try:
        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(temp_path)])

        # Parse edited content
        edited_content = temp_path.read_text()
        # Remove comment lines for parsing
        lines = [l for l in edited_content.split('\n') if not l.strip().startswith('#')]
        edited = yaml.safe_load('\n'.join(lines))

        # Validate that we have actual content
        if edited is None:
            console.print(error("Settings section is empty after editing. No changes made."))
            raise typer.Exit(1)

        # Merge back
        if set_settings_value(settings_data, path, edited):
            settings_path.write_text(yaml.dump(settings_data, default_flow_style=False, sort_keys=False))
            console.print(success(f"Updated {path}"))
        else:
            console.print(error("Failed to update settings"))
    except yaml.YAMLError as e:
        console.print(error(f"Invalid YAML: {e}"))
        raise typer.Exit(1)
    finally:
        temp_path.unlink(missing_ok=True)


@settings_app.command("add")
def settings_add(
    add_type: str = typer.Argument(
        ...,
        help="What to add: media, approach, or source",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Internal name (e.g., 'papers', 'serendipitous')",
    ),
    display: Optional[str] = typer.Option(
        None,
        "--display",
        "-d",
        help="Display name (e.g., 'Academic Papers')",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Interactive wizard (prompts for all fields)",
    ),
    source_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Source type: loader or mcp (only for 'source')",
    ),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        help="File path (for loader sources)",
    ),
) -> None:
    """Add a new media type, approach, or context source.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity settings add media -i                     [dim]# Interactive[/dim]
      [dim]$[/dim] serendipity settings add media -n papers -d "Papers"  [dim]# Quick add[/dim]
      [dim]$[/dim] serendipity settings add approach -n lucky            [dim]# New approach[/dim]
      [dim]$[/dim] serendipity settings add source -n notes -t loader    [dim]# Loader source[/dim]
      [dim]$[/dim] serendipity settings add source -n custom -t mcp      [dim]# MCP source[/dim]
    """
    import yaml

    from serendipity import settings as settings_module

    valid_types = ["media", "approach", "source"]
    if add_type not in valid_types:
        console.print(error(f"Unknown type: {add_type}"))
        console.print(f"[dim]Valid types: {', '.join(valid_types)}[/dim]")
        raise typer.Exit(1)

    # Interactive mode or missing required fields
    if interactive or not name:
        if add_type == "media":
            _add_media_interactive()
        elif add_type == "approach":
            _add_approach_interactive()
        elif add_type == "source":
            _add_source_interactive(source_type)
        return

    # Non-interactive mode with explicit options
    if add_type == "media":
        new_config = settings_module.add_media(
            name=name,
            display_name=display,
        )
        console.print(success(f"Added media type '{name}'"))
        console.print(Panel(yaml.dump({name: new_config}, default_flow_style=False), title="Configuration"))

    elif add_type == "approach":
        new_config = settings_module.add_approach(
            name=name,
            display_name=display,
        )
        console.print(success(f"Added approach '{name}'"))
        console.print(Panel(yaml.dump({name: new_config}, default_flow_style=False), title="Configuration"))

    elif add_type == "source":
        if not source_type:
            console.print(error("Source type required. Use --type loader or --type mcp"))
            raise typer.Exit(1)
        if source_type not in ["loader", "mcp"]:
            console.print(error(f"Invalid source type: {source_type}"))
            raise typer.Exit(1)

        if source_type == "loader":
            if not path:
                console.print(error("Path required for loader sources. Use --path"))
                raise typer.Exit(1)
            new_config = settings_module.add_loader_source(name=name, path=path)
        else:
            new_config = settings_module.add_mcp_source(name=name)

        console.print(success(f"Added {source_type} source '{name}'"))
        console.print(Panel(yaml.dump({name: new_config}, default_flow_style=False), title="Configuration"))


def _add_media_interactive() -> None:
    """Interactive wizard for adding a media type."""
    import yaml

    from serendipity import settings as settings_module

    console.print(Panel(
        "Add a new media type (e.g., papers, courses, newsletters)",
        title="Add Media Type",
        border_style="blue",
    ))

    name = questionary.text(
        "Internal name (lowercase, no spaces):",
        validate=lambda x: bool(x.strip() and x.replace("_", "").isalnum()),
    ).ask()
    if not name:
        console.print(warning("Cancelled"))
        return

    default_display = name.replace("_", " ").title()
    display_name = questionary.text(
        "Display name:",
        default=default_display,
    ).ask()
    if not display_name:
        display_name = default_display

    search_hints = questionary.text(
        "Search hints (use {query} placeholder):",
        default="{query}",
    ).ask()
    if not search_hints:
        search_hints = "{query}"

    prompt_hint = questionary.text(
        "Prompt hint (guidance for the agent):",
        default=f"Search for {display_name.lower()}.",
    ).ask()

    # Add the media type
    new_config = settings_module.add_media(
        name=name,
        display_name=display_name,
        search_hints=search_hints,
        prompt_hint=prompt_hint or "",
    )

    console.print(success(f"Added media type '{name}'"))
    console.print(Panel(yaml.dump({name: new_config}, default_flow_style=False), title="Configuration"))


def _add_approach_interactive() -> None:
    """Interactive wizard for adding an approach."""
    import yaml

    from serendipity import settings as settings_module

    console.print(Panel(
        "Add a new discovery approach (how to find content)",
        title="Add Approach",
        border_style="blue",
    ))

    name = questionary.text(
        "Internal name (lowercase, no spaces):",
        validate=lambda x: bool(x.strip() and x.replace("_", "").isalnum()),
    ).ask()
    if not name:
        console.print(warning("Cancelled"))
        return

    default_display = name.replace("_", " ").title()
    display_name = questionary.text(
        "Display name:",
        default=default_display,
    ).ask()
    if not display_name:
        display_name = default_display

    prompt_hint = questionary.text(
        "Prompt hint (guidance for this approach):",
        default="- Find unique and interesting content",
    ).ask()

    new_config = settings_module.add_approach(
        name=name,
        display_name=display_name,
        prompt_hint=prompt_hint or "",
    )

    console.print(success(f"Added approach '{name}'"))
    console.print(Panel(yaml.dump({name: new_config}, default_flow_style=False), title="Configuration"))


def _add_source_interactive(preset_type: Optional[str] = None) -> None:
    """Interactive wizard for adding a context source."""
    import yaml

    from serendipity import settings as settings_module

    console.print(Panel(
        "Add a new context source (where to get user profile data)",
        title="Add Context Source",
        border_style="blue",
    ))

    # Determine source type
    if preset_type and preset_type in ["loader", "mcp"]:
        source_type = preset_type
    else:
        source_type = questionary.select(
            "Source type:",
            choices=[
                questionary.Choice("loader - Load content from a file", value="loader"),
                questionary.Choice("mcp - Connect to an MCP server", value="mcp"),
            ],
        ).ask()
        if not source_type:
            console.print(warning("Cancelled"))
            return

    name = questionary.text(
        "Internal name (lowercase, no spaces):",
        validate=lambda x: bool(x.strip() and x.replace("_", "").isalnum()),
    ).ask()
    if not name:
        console.print(warning("Cancelled"))
        return

    description = questionary.text(
        "Description:",
        default=f"Content from {name}",
    ).ask()

    if source_type == "loader":
        path = questionary.text(
            "File path (supports ~):",
            default=f"~/.serendipity/{name}.md",
        ).ask()
        if not path:
            console.print(warning("Cancelled"))
            return

        new_config = settings_module.add_loader_source(
            name=name,
            path=path,
            description=description,
        )
    else:  # mcp
        server_url = questionary.text(
            "Server URL template:",
            default="http://localhost:{port}/mcp/",
        ).ask()

        cli_command = questionary.text(
            "CLI command to start server:",
            default=name,
        ).ask()

        port = questionary.text(
            "Default port:",
            default="8080",
            validate=lambda x: x.isdigit(),
        ).ask()

        new_config = settings_module.add_mcp_source(
            name=name,
            server_url=server_url or "http://localhost:{port}/mcp/",
            cli_command=cli_command,
            port=int(port) if port else 8080,
            description=description,
        )

    console.print(success(f"Added {source_type} source '{name}'"))
    console.print(Panel(yaml.dump({name: new_config}, default_flow_style=False), title="Configuration"))


# =============================================================================
# Prompts management
# =============================================================================

VALID_PROMPTS = {
    "discovery": ("discovery.txt", get_discovery_prompt),
    "frontend_design": ("frontend_design.txt", get_frontend_design),
    "system": ("system.txt", get_system_prompt),
}


@settings_app.command("prompts")
def settings_prompts(
    edit: Optional[str] = typer.Option(
        None,
        "--edit",
        "-e",
        help="Edit a prompt in $EDITOR (discovery, frontend_design, system)",
    ),
    reset: Optional[str] = typer.Option(
        None,
        "--reset",
        "-r",
        help="Reset a prompt to package default",
    ),
    show: Optional[str] = typer.Option(
        None,
        "--show",
        "-s",
        help="Show prompt content",
    ),
) -> None:
    """Manage system prompts that control agent behavior.

    These prompts define how the discovery agent searches and recommends content.
    Edit them to customize the agent's behavior.

    [bold cyan]PROMPTS[/bold cyan]:
      discovery       - Main instructions for finding content
      frontend_design - CSS generation guidelines
      system          - Core system prompt (search behavior)

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity settings prompts                    [dim]# List all prompts[/dim]
      [dim]$[/dim] serendipity settings prompts --show discovery   [dim]# View content[/dim]
      [dim]$[/dim] serendipity settings prompts --edit discovery   [dim]# Edit in $EDITOR[/dim]
      [dim]$[/dim] serendipity settings prompts --reset discovery  [dim]# Reset to default[/dim]
    """
    storage = StorageManager()
    storage.ensure_dirs()

    if edit:
        if edit not in VALID_PROMPTS:
            console.print(error(f"Unknown prompt: {edit}"))
            console.print(f"[dim]Valid prompts: {', '.join(VALID_PROMPTS.keys())}[/dim]")
            raise typer.Exit(1)

        filename, default_getter = VALID_PROMPTS[edit]
        prompt_path = storage.get_prompt_path(filename, default_getter())

        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(prompt_path)])
        console.print(success(f"Prompt saved to {prompt_path}"))
        return

    if reset:
        if reset not in VALID_PROMPTS:
            console.print(error(f"Unknown prompt: {reset}"))
            console.print(f"[dim]Valid prompts: {', '.join(VALID_PROMPTS.keys())}[/dim]")
            raise typer.Exit(1)

        filename, default_getter = VALID_PROMPTS[reset]
        prompt_path = storage.prompts_dir / filename

        if not prompt_path.exists():
            console.print(warning(f"Prompt '{reset}' is already using package default"))
            return

        if not typer.confirm(f"Reset '{reset}' to package default?"):
            console.print(warning("Cancelled"))
            return

        prompt_path.write_text(default_getter())
        console.print(success(f"Reset '{reset}' to package default"))
        return

    if show:
        if show not in VALID_PROMPTS:
            console.print(error(f"Unknown prompt: {show}"))
            console.print(f"[dim]Valid prompts: {', '.join(VALID_PROMPTS.keys())}[/dim]")
            raise typer.Exit(1)

        filename, default_getter = VALID_PROMPTS[show]
        prompt_path = storage.prompts_dir / filename

        if prompt_path.exists():
            content = prompt_path.read_text()
            is_custom = content != default_getter()
            status = "[yellow]custom[/yellow]" if is_custom else "[dim]default[/dim]"
        else:
            content = default_getter()
            status = "[dim]default[/dim]"

        console.print(Panel(
            content,
            title=f"{show} ({status})",
            border_style="blue",
        ))
        return

    # Default: list all prompts with status
    console.print("\n[bold]Prompts[/bold] (agent instructions):")
    for name, (filename, default_getter) in VALID_PROMPTS.items():
        prompt_path = storage.prompts_dir / filename
        if prompt_path.exists():
            is_custom = prompt_path.read_text() != default_getter()
            status = "[yellow]custom[/yellow]" if is_custom else "[dim]default[/dim]"
        else:
            status = "[dim]default[/dim]"
        console.print(f"  [cyan]{name}[/cyan]: {status}")

    console.print(f"\n[dim]Prompts: {storage.prompts_dir}[/dim]")
    console.print(f"[dim]Edit: serendipity settings prompts --edit <name>[/dim]")


@settings_app.command("style")
def settings_style(
    edit: bool = typer.Option(
        False,
        "--edit",
        "-e",
        help="Edit the CSS stylesheet in $EDITOR",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        "-r",
        help="Reset stylesheet to package default",
    ),
    show: bool = typer.Option(
        False,
        "--show",
        "-s",
        help="Show current stylesheet",
    ),
) -> None:
    """Manage the CSS stylesheet for recommendations.

    The stylesheet controls the visual appearance of your recommendations page.
    Edit it to customize colors, fonts, layout, etc.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity settings style          [dim]# Show status[/dim]
      [dim]$[/dim] serendipity settings style --edit   [dim]# Edit in $EDITOR[/dim]
      [dim]$[/dim] serendipity settings style --reset  [dim]# Reset to default[/dim]
      [dim]$[/dim] serendipity settings style --show   [dim]# View current CSS[/dim]
    """
    storage = StorageManager()
    storage.ensure_dirs()
    default_css = get_default_style()

    if edit:
        style_path = storage.get_style_path(default_css)
        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(style_path)])
        console.print(success(f"Style saved to {style_path}"))
        return

    if reset:
        if not storage.style_path.exists():
            console.print(warning("Style is already using package default"))
            return

        if not typer.confirm("Reset stylesheet to package default?"):
            console.print(warning("Cancelled"))
            return

        storage.style_path.write_text(default_css)
        console.print(success("Reset stylesheet to package default"))
        return

    if show:
        if storage.style_path.exists():
            content = storage.style_path.read_text()
            is_custom = content != default_css
            status = "[yellow]custom[/yellow]" if is_custom else "[dim]default[/dim]"
        else:
            content = default_css
            status = "[dim]default[/dim]"

        console.print(Panel(
            content,
            title=f"style.css ({status})",
            border_style="blue",
        ))
        return

    # Default: show status
    if storage.style_path.exists():
        is_custom = storage.style_path.read_text() != default_css
        status = "[yellow]custom[/yellow]" if is_custom else "[dim]default[/dim]"
    else:
        status = "[dim]default[/dim]"

    console.print(f"\n[bold]Stylesheet[/bold]: {status}")
    console.print(f"[dim]Path: {storage.style_path}[/dim]")
    console.print(f"[dim]Edit: serendipity settings style --edit[/dim]")


# =============================================================================
# New generic profile get/edit commands
# =============================================================================


@profile_app.command("get")
def profile_get(
    source_name: str = typer.Argument(..., help="Name of the context source"),
    # History-specific flags
    liked: bool = typer.Option(False, "--liked", help="[history] Show only liked items"),
    disliked: bool = typer.Option(False, "--disliked", help="[history] Show only disliked items"),
    limit: int = typer.Option(20, "--limit", "-n", help="[history] Number of items to show"),
    # Learnings-specific flags
    interactive: bool = typer.Option(False, "--interactive", "-i", help="[learnings] Interactive wizard"),
    # Universal flags
    clear: bool = typer.Option(False, "--clear", help="Clear source content"),
) -> None:
    """View or manage a context source.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile get taste              [dim]# View taste profile[/dim]
      [dim]$[/dim] serendipity profile get history --liked    [dim]# View liked items[/dim]
      [dim]$[/dim] serendipity profile get history -n 50      [dim]# View 50 recent items[/dim]
      [dim]$[/dim] serendipity profile get learnings -i       [dim]# Interactive extraction[/dim]
      [dim]$[/dim] serendipity profile get taste --clear      [dim]# Clear taste profile[/dim]
      [dim]$[/dim] serendipity profile get whorl              [dim]# View MCP source config[/dim]
    """
    storage = StorageManager()
    storage.ensure_dirs()
    settings = storage.load_config()

    if source_name not in settings.context_sources:
        console.print(error(f"Unknown source: {source_name}"))
        console.print(f"[dim]Available: {', '.join(settings.context_sources.keys())}[/dim]")
        raise typer.Exit(1)

    source_config = settings.context_sources[source_name]

    # Route to appropriate handler
    if source_name == "history":
        _handle_profile_history(storage, liked=liked, disliked=disliked, limit=limit, clear=clear)
    elif source_name == "learnings":
        _handle_profile_learnings(storage, interactive=interactive, clear=clear, edit=False)
    elif source_config.type == "mcp":
        if clear:
            console.print(error(f"'{source_name}' is an MCP source (cannot be cleared)."))
            raise typer.Exit(1)
        _handle_profile_mcp_source(source_config)
    else:
        # Check if it's a file-based loader
        is_editable, file_path = is_source_editable(source_config)
        if is_editable:
            _handle_profile_file_source(storage, source_config, file_path, clear=clear, edit=False)
        else:
            if clear:
                console.print(error(f"'{source_name}' is not clearable (not file-based)."))
                raise typer.Exit(1)
            _handle_profile_generic_loader(storage, source_config)


@profile_app.command("edit")
def profile_edit(
    source_name: str = typer.Argument(..., help="Name of the context source"),
) -> None:
    """Edit a context source in $EDITOR.

    Only file-based sources can be edited. MCP sources and dynamic loaders
    (like style_guidance) are read-only.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile edit taste       [dim]# Edit taste.md[/dim]
      [dim]$[/dim] serendipity profile edit learnings   [dim]# Edit learnings.md[/dim]
      [dim]$[/dim] serendipity profile edit notes       [dim]# Edit notes.md[/dim]
    """
    storage = StorageManager()
    storage.ensure_dirs()
    settings = storage.load_config()

    if source_name not in settings.context_sources:
        console.print(error(f"Unknown source: {source_name}"))
        console.print(f"[dim]Available: {', '.join(settings.context_sources.keys())}[/dim]")
        raise typer.Exit(1)

    source_config = settings.context_sources[source_name]

    # Special handling for learnings (has its own edit logic)
    if source_name == "learnings":
        _handle_profile_learnings(storage, interactive=False, clear=False, edit=True)
        return

    # Check if source is editable
    if source_config.type == "mcp":
        console.print(error(f"'{source_name}' is an MCP source (read-only)."))
        console.print(f"[dim]Use 'serendipity profile get {source_name}' to view its configuration.[/dim]")
        raise typer.Exit(1)

    is_editable, file_path = is_source_editable(source_config)
    if not is_editable:
        console.print(error(f"'{source_name}' is not editable (no file path)."))
        console.print(f"[dim]This source uses loader: {source_config.raw_config.get('loader', 'unknown')}[/dim]")
        raise typer.Exit(1)

    _handle_profile_file_source(storage, source_config, file_path, clear=False, edit=True)

def _learnings_interactive_wizard(storage: StorageManager) -> None:
    """Interactive wizard for learning extraction."""
    from serendipity.search import HistorySearcher

    console.print(Panel(
        "Extract patterns from your likes/dislikes into reusable learnings",
        title="Learning Extraction Wizard",
        border_style="blue",
    ))

    # Step 1: Choose workflow
    workflow = questionary.select(
        "What would you like to do?",
        choices=[
            questionary.Choice(
                "Extract learnings from likes/dislikes (Claude proposes)",
                value="extract",
            ),
            questionary.Choice(
                "Write a learning and auto-tag matching items",
                value="write",
            ),
            questionary.Choice(
                "View/edit existing learnings",
                value="view",
            ),
            questionary.Choice(
                "Cancel",
                value="cancel",
            ),
        ],
    ).ask()

    if workflow == "cancel" or workflow is None:
        console.print(warning("Cancelled"))
        return

    if workflow == "view":
        learnings_content = storage.load_learnings()
        if learnings_content.strip():
            console.print(Panel(learnings_content, title="Current Learnings", border_style="blue"))
        else:
            console.print("[dim]No learnings yet.[/dim]")
        if questionary.confirm("Edit learnings in $EDITOR?", default=False).ask():
            editor = os.environ.get("EDITOR", "vim")
            if not storage.learnings_path.exists():
                storage.learnings_path.write_text("# My Discovery Learnings\n\n## Likes\n\n## Dislikes\n")
            subprocess.run([editor, str(storage.learnings_path)])
        return

    if workflow == "extract":
        _extract_learning_workflow(storage)
    elif workflow == "write":
        _write_learning_workflow(storage)


def _extract_learning_workflow(storage: StorageManager) -> None:
    """Workflow: Claude proposes learnings from selected items."""
    from serendipity.rules import generate_rule
    from serendipity.search import HistorySearcher

    # Step 2: Choose feedback type
    unextracted_liked = storage.get_unextracted_entries("liked")
    unextracted_disliked = storage.get_unextracted_entries("disliked")

    if not unextracted_liked and not unextracted_disliked:
        console.print(warning("No unextracted items found. All your likes/dislikes are already in learnings."))
        return

    choices = []
    if unextracted_liked:
        choices.append(questionary.Choice(
            f"Likes ({len(unextracted_liked)} unextracted)",
            value="liked",
        ))
    if unextracted_disliked:
        choices.append(questionary.Choice(
            f"Dislikes ({len(unextracted_disliked)} unextracted)",
            value="disliked",
        ))
    choices.append(questionary.Choice("Cancel", value="cancel"))

    feedback_type = questionary.select(
        "Select feedback type:",
        choices=choices,
    ).ask()

    if feedback_type == "cancel" or feedback_type is None:
        console.print(warning("Cancelled"))
        return

    entries = unextracted_liked if feedback_type == "liked" else unextracted_disliked
    searcher = HistorySearcher(entries)

    # Step 3: Search and select items
    while True:
        search_query = questionary.text(
            "Search items (or press Enter to see all):",
            default="",
        ).ask()

        if search_query is None:
            console.print(warning("Cancelled"))
            return

        if search_query.strip():
            results = searcher.search(search_query.strip(), limit=30)
        else:
            results = entries[:30]

        if not results:
            console.print(warning("No matches found."))
            continue

        # Build selection choices
        item_choices = []
        for e in results:
            url_short = e.url[:50] + "..." if len(e.url) > 50 else e.url
            reason_short = e.reason[:40] + "..." if len(e.reason) > 40 else e.reason
            label = f"{url_short} - \"{reason_short}\""
            item_choices.append(questionary.Choice(label, value=e))

        selected = questionary.checkbox(
            "Select items to include (space to toggle):",
            choices=item_choices,
        ).ask()

        if selected is None:
            console.print(warning("Cancelled"))
            return

        if not selected:
            retry = questionary.confirm("No items selected. Search again?", default=True).ask()
            if not retry:
                console.print(warning("Cancelled"))
                return
            continue

        break

    # Step 4: Generate learning with Claude
    console.print(info(f"Generating learning from {len(selected)} items..."))

    try:
        learning = asyncio.run(generate_rule(selected, feedback_type))
    except Exception as e:
        console.print(error(f"Failed to generate learning: {e}"))
        return

    if not learning:
        console.print(error("Failed to generate learning. Try selecting different items."))
        return

    # Step 5: Show and confirm
    console.print()
    console.print(Panel(
        f"### {learning.title}\n{learning.content}",
        title="Proposed Learning",
        border_style="green",
    ))

    action = questionary.select(
        "Accept this learning?",
        choices=[
            questionary.Choice("Accept and save", value="accept"),
            questionary.Choice("Edit before saving", value="edit"),
            questionary.Choice("Cancel", value="cancel"),
        ],
    ).ask()

    if action == "cancel" or action is None:
        console.print(warning("Cancelled"))
        return

    if action == "edit":
        edited_title = questionary.text("Learning title:", default=learning.title).ask()
        edited_content = questionary.text("Learning content:", default=learning.content).ask()
        if edited_title and edited_content:
            learning.title = edited_title
            learning.content = edited_content

    # Save learning and mark items as extracted
    storage.append_learning(learning.title, learning.content, learning.rule_type)
    urls = [e.url for e in selected]
    count = storage.mark_extracted(urls)

    console.print(success(f"Learning saved to {storage.learnings_path}"))
    console.print(success(f"Marked {count} items as extracted"))


def _write_learning_workflow(storage: StorageManager) -> None:
    """Workflow: User writes learning, Claude finds matching items."""
    from serendipity.rules import find_matching_items

    # Step 1: Get learning type
    learning_type = questionary.select(
        "What type of learning?",
        choices=[
            questionary.Choice("Like (things I enjoy)", value="like"),
            questionary.Choice("Dislike (things to avoid)", value="dislike"),
        ],
    ).ask()

    if learning_type is None:
        console.print(warning("Cancelled"))
        return

    # Step 2: Get learning text
    console.print("\n[dim]Write a description of the pattern (can be a few sentences):[/dim]")
    learning_text = questionary.text(
        "Learning:",
        multiline=False,
    ).ask()

    if not learning_text or not learning_text.strip():
        console.print(warning("Cancelled"))
        return

    # Step 3: Find matching items
    feedback = "liked" if learning_type == "like" else "disliked"
    entries = storage.get_unextracted_entries(feedback)

    if not entries:
        console.print(warning(f"No unextracted {feedback} items to match against."))
        # Still save the learning
        title = questionary.text("Learning title (short):", default="").ask()
        if title:
            storage.append_learning(title, learning_text.strip(), learning_type)
            console.print(success("Learning saved (no items to mark as extracted)"))
        return

    console.print(info(f"Finding matching items among {len(entries)} {feedback} entries..."))

    try:
        matching_urls = asyncio.run(find_matching_items(learning_text, entries))
    except Exception as e:
        console.print(error(f"Failed to find matches: {e}"))
        matching_urls = []

    if matching_urls:
        console.print(success(f"Found {len(matching_urls)} matching items:"))
        for url in matching_urls[:10]:
            url_short = url[:60] + "..." if len(url) > 60 else url
            console.print(f"  • {url_short}")
        if len(matching_urls) > 10:
            console.print(f"  ... and {len(matching_urls) - 10} more")

        confirm = questionary.select(
            "Confirm these items as extracted?",
            choices=[
                questionary.Choice("Yes, mark all as extracted", value="yes"),
                questionary.Choice("No, save learning without marking", value="no"),
                questionary.Choice("Cancel", value="cancel"),
            ],
        ).ask()

        if confirm == "cancel" or confirm is None:
            console.print(warning("Cancelled"))
            return

        mark_items = confirm == "yes"
    else:
        console.print(warning("No matching items found."))
        mark_items = False

    # Step 4: Get title and save
    title = questionary.text(
        "Learning title (short):",
        default="",
    ).ask()

    if not title:
        console.print(warning("Cancelled - no title provided"))
        return

    storage.append_learning(title, learning_text.strip(), learning_type)
    console.print(success(f"Learning saved to {storage.learnings_path}"))

    if mark_items and matching_urls:
        count = storage.mark_extracted(matching_urls)
        console.print(success(f"Marked {count} items as extracted"))


# Profile management commands (multi-profile support)

@profile_app.command("list")
def profile_list() -> None:
    """List all available profiles.

    Shows all profiles with the active one marked with *.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile list
    """
    pm = ProfileManager()
    profiles = pm.list_profiles()
    active = pm.get_active_profile()

    console.print("\n[bold]Profiles[/bold]")
    for name in profiles:
        marker = " *" if name == active else ""
        console.print(f"  {name}{marker}")

    console.print(f"\n[dim]Active: {active}[/dim]")
    if os.environ.get("SERENDIPITY_PROFILE"):
        console.print(f"[dim](via SERENDIPITY_PROFILE env var)[/dim]")


@profile_app.command("create")
def profile_create(
    name: str = typer.Argument(..., help="Name for the new profile"),
    from_profile: Optional[str] = typer.Option(
        None,
        "--from",
        "-f",
        help="Copy from existing profile",
    ),
) -> None:
    """Create a new profile.

    Creates an empty profile or copies from an existing one.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile create work
      [dim]$[/dim] serendipity profile create minimalist --from default
    """
    pm = ProfileManager()

    try:
        path = pm.create_profile(name, from_profile=from_profile)
        if from_profile:
            console.print(success(f"Created profile '{name}' (copied from '{from_profile}')"))
        else:
            console.print(success(f"Created profile '{name}'"))
        console.print(f"[dim]{path}[/dim]")
        console.print(f"\n[dim]Switch to it: serendipity profile use {name}[/dim]")
    except ValueError as e:
        console.print(error(str(e)))
        raise typer.Exit(1)


@profile_app.command("use")
def profile_use(
    name: str = typer.Argument(..., help="Profile to switch to"),
) -> None:
    """Switch to a different profile.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile use work
      [dim]$[/dim] serendipity profile use default
    """
    pm = ProfileManager()

    try:
        pm.set_active_profile(name)
        console.print(success(f"Switched to profile '{name}'"))
    except ValueError as e:
        console.print(error(str(e)))
        console.print(f"[dim]Available profiles: {', '.join(pm.list_profiles())}[/dim]")
        raise typer.Exit(1)


@profile_app.command("delete")
def profile_delete(
    name: str = typer.Argument(..., help="Profile to delete"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Delete a profile.

    Cannot delete the currently active profile. Switch to another first.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile delete old-profile
      [dim]$[/dim] serendipity profile delete temp --force
    """
    pm = ProfileManager()

    if not pm.profile_exists(name):
        console.print(error(f"Profile '{name}' does not exist"))
        raise typer.Exit(1)

    if not force:
        if not typer.confirm(f"Delete profile '{name}'? This cannot be undone."):
            console.print(warning("Cancelled"))
            return

    try:
        pm.delete_profile(name)
        console.print(success(f"Deleted profile '{name}'"))
    except ValueError as e:
        console.print(error(str(e)))
        raise typer.Exit(1)


@profile_app.command("rename")
def profile_rename(
    old_name: str = typer.Argument(..., help="Current profile name"),
    new_name: str = typer.Argument(..., help="New profile name"),
) -> None:
    """Rename a profile.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile rename work business
    """
    pm = ProfileManager()

    try:
        pm.rename_profile(old_name, new_name)
        console.print(success(f"Renamed '{old_name}' to '{new_name}'"))
    except ValueError as e:
        console.print(error(str(e)))
        raise typer.Exit(1)


@profile_app.command("export")
def profile_export(
    name: Optional[str] = typer.Argument(
        None,
        help="Profile to export (defaults to active profile)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (defaults to {name}.tar.gz)",
    ),
) -> None:
    """Export a profile to a tar.gz archive.

    Exports the profile directory for sharing or backup.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile export                    [dim]# Export active profile[/dim]
      [dim]$[/dim] serendipity profile export work               [dim]# Export specific profile[/dim]
      [dim]$[/dim] serendipity profile export work -o backup.tar.gz
    """
    pm = ProfileManager()
    profile_name = name or pm.get_active_profile()

    try:
        output_path = pm.export_profile(profile_name, output)
        console.print(success(f"Exported '{profile_name}' to {output_path}"))
    except ValueError as e:
        console.print(error(str(e)))
        raise typer.Exit(1)


@profile_app.command("import")
def profile_import(
    archive: Path = typer.Argument(..., help="Path to the .tar.gz archive"),
    name: Optional[str] = typer.Option(
        None,
        "--as",
        help="Import with a different name",
    ),
) -> None:
    """Import a profile from a tar.gz archive.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile import friend-taste.tar.gz
      [dim]$[/dim] serendipity profile import backup.tar.gz --as restored
    """
    pm = ProfileManager()

    try:
        imported_name = pm.import_profile(archive, name)
        console.print(success(f"Imported profile '{imported_name}'"))
        console.print(f"\n[dim]Switch to it: serendipity profile use {imported_name}[/dim]")
    except ValueError as e:
        console.print(error(str(e)))
        raise typer.Exit(1)


def cli() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    cli()
