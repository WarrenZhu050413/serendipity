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
from serendipity.resources import get_base_template

# Config setting descriptions
CONFIG_DESCRIPTIONS = {
    "taste_path": "Path to your taste profile (markdown file with your aesthetic preferences)",
    "template_path": "Path to HTML template (copied from package default on first use)",
    "history_enabled": "Track recommendations to avoid repeats and learn from feedback",
    "max_recent_history": "Number of recent items to include in context (avoids repeating)",
    "feedback_server_port": "Port for the HTML feedback server (localhost)",
    "default_model": "Claude model to use (haiku=fast, sonnet=balanced, opus=best)",
    "default_n1": "Default number of convergent recommendations (more of what you like)",
    "default_n2": "Default number of divergent recommendations (expand your taste)",
    "html_style": "HTML styling preference (null=auto-generate based on taste)",
    "max_thinking_tokens": "Max tokens for extended thinking (null=disabled, 10000=default when enabled)",
}
from serendipity.storage import Config, HistoryEntry, StorageManager

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

console = Console()


@app.callback()
def callback(ctx: typer.Context) -> None:
    """Personal Serendipity Engine - discover convergent and divergent content recommendations."""
    # If no subcommand was invoked, run discover with defaults ("surprise me" mode)
    if ctx.invoked_subcommand is None:
        # Call discover_cmd directly with default values
        discover_cmd(
            file_path=None,
            n1=None,
            n2=None,
            paste=False,
            interactive=False,
            model=None,
            output_format="html",
            verbose=False,
            no_history=False,
            no_taste=False,
            whorl=False,
            thinking=None,
        )


@profile_app.callback()
def profile_callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show word counts per section",
    ),
) -> None:
    """Preview your profile - what Claude knows about you.

    Shows taste, learnings, recent history, and pending feedback.
    """
    if ctx.invoked_subcommand is not None:
        return

    storage = StorageManager()
    storage.ensure_dirs()

    # Run migration if needed
    migrations = storage.migrate_if_needed()
    for msg in migrations:
        console.print(f"[yellow]{msg}[/yellow]")

    output_lines = []

    # Taste section
    taste = storage.load_taste()
    if taste.strip():
        # Check if it's still the default template
        if "Describe your aesthetic preferences" in taste and "Examples:" in taste:
            taste_display = "[dim]Default template (not customized)[/dim]"
            taste_words = 0
        else:
            taste_words = storage.count_words(taste)
            taste_display = taste[:500] + "..." if len(taste) > 500 else taste
    else:
        taste_display = "[dim]Not set[/dim]"
        taste_words = 0

    header = "TASTE" + (f" ({taste_words} words)" if verbose and taste_words else "")
    output_lines.append(f"[bold cyan]{header}[/bold cyan]")
    output_lines.append(taste_display)
    output_lines.append("")

    # Learnings section
    learnings_content = storage.load_learnings()
    if learnings_content.strip():
        learnings_words = storage.count_words(learnings_content)
        learnings_display = learnings_content[:500] + "..." if len(learnings_content) > 500 else learnings_content
    else:
        learnings_display = "[dim]No learnings yet[/dim]"
        learnings_words = 0

    header = "LEARNINGS" + (f" ({learnings_words} words)" if verbose and learnings_words else "")
    output_lines.append(f"[bold cyan]{header}[/bold cyan]")
    output_lines.append(learnings_display)
    output_lines.append("")

    # Recent history section
    recent = storage.load_recent_history(20)
    header = "RECENT HISTORY" + (f" ({len(recent)} items)" if recent else "")
    output_lines.append(f"[bold cyan]{header}[/bold cyan]")
    if recent:
        for entry in recent[-5:]:  # Show last 5
            feedback = ""
            if entry.feedback == "liked":
                feedback = " [green](liked)[/green]"
            elif entry.feedback == "disliked":
                feedback = " [red](disliked)[/red]"
            output_lines.append(f"  - {entry.url[:60]}{'...' if len(entry.url) > 60 else ''}{feedback}")
        if len(recent) > 5:
            output_lines.append(f"  [dim]... and {len(recent) - 5} more[/dim]")
    else:
        output_lines.append("[dim]No history[/dim]")
    output_lines.append("")

    # Unextracted feedback section
    liked = storage.get_unextracted_entries(feedback="liked")
    disliked = storage.get_unextracted_entries(feedback="disliked")
    output_lines.append(f"[bold cyan]PENDING FEEDBACK[/bold cyan]")
    output_lines.append(f"  Unextracted likes: {len(liked)}")
    output_lines.append(f"  Unextracted dislikes: {len(disliked)}")

    # Total word count
    if verbose:
        total_words = taste_words + learnings_words
        output_lines.append("")
        output_lines.append(f"[dim]Total context: ~{total_words} words (excluding history)[/dim]")

    console.print(Panel(
        "\n".join(output_lines),
        title="Your Profile",
        border_style="blue",
    ))

    console.print("\n[bold]Subcommands:[/bold]")
    console.print("  serendipity profile taste      # Edit your taste profile")
    console.print("  serendipity profile history    # View history")
    console.print("  serendipity profile learnings  # Manage learnings")


# Rich formatting helpers
def info(text: str) -> str:
    return f"[cyan]{text}[/cyan]"


def error(text: str) -> str:
    return f"[red]{text}[/red]"


def success(text: str) -> str:
    return f"[green]{text}[/green]"


def warning(text: str) -> str:
    return f"[yellow]{text}[/yellow]"


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
) -> None:
    """Start the feedback server in a background thread."""
    from serendipity.server import FeedbackServer

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

        await server.start(port)

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
            console.print(f"[red]Feedback server error: {e}[/red]")
            traceback.print_exc()

    thread = threading.Thread(target=thread_target, daemon=True)
    thread.start()

    # Wait for server to be ready
    import urllib.request
    import time
    for _ in range(10):  # Try for up to 1 second
        try:
            req = urllib.request.Request(f"http://localhost:{port}/health")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)
    else:
        console.print("[yellow]Warning: Feedback server may not be ready[/yellow]")

    return thread


@app.command(name="discover")
def discover_cmd(
    file_path: Optional[Path] = typer.Argument(
        None,
        help="Path to context file (use '-' for stdin)",
    ),
    n1: Optional[int] = typer.Option(
        None,
        "--n1",
        help="Number of convergent recommendations (default from config)",
    ),
    n2: Optional[int] = typer.Option(
        None,
        "--n2",
        help="Number of divergent recommendations (default from config)",
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
    no_history: bool = typer.Option(
        False,
        "--no-history",
        help="Don't use or save history for this run",
    ),
    no_taste: bool = typer.Option(
        False,
        "--no-taste",
        help="Don't include taste profile for this run",
    ),
    whorl: bool = typer.Option(
        False,
        "--whorl",
        "-w",
        help="Enable Whorl integration (search personal knowledge base for context)",
    ),
    thinking: Optional[int] = typer.Option(
        None,
        "--thinking",
        "-t",
        help="Enable extended thinking with specified token budget (e.g., 10000)",
    ),
) -> None:
    """Discover convergent and divergent content recommendations.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity                           [dim]# Surprise me (uses profile)[/dim]
      [dim]$[/dim] serendipity "I'm in the mood for..."  [dim]# Quick prompt[/dim]
      [dim]$[/dim] serendipity notes.md                  [dim]# From file[/dim]
      [dim]$[/dim] serendipity -p                        [dim]# From clipboard[/dim]
      [dim]$[/dim] serendipity -i                        [dim]# Open editor[/dim]
      [dim]$[/dim] serendipity --n1 3 --n2 8             [dim]# Custom counts[/dim]
      [dim]$[/dim] serendipity -o terminal               [dim]# No browser[/dim]
      [dim]$[/dim] serendipity -w                        [dim]# With Whorl knowledge base[/dim]
    """
    # Load storage and config
    storage = StorageManager()
    storage.ensure_dirs()
    config = storage.load_config()

    # Run migration if needed
    migrations = storage.migrate_if_needed()
    for msg in migrations:
        console.print(f"[yellow]{msg}[/yellow]")

    # Use config defaults if not specified
    if model is None:
        model = config.default_model
    if n1 is None:
        n1 = config.default_n1
    if n2 is None:
        n2 = config.default_n2
    # Use CLI thinking value, or fall back to config
    max_thinking_tokens = thinking if thinking is not None else config.max_thinking_tokens

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

    # Build context augmentation
    context_augmentation = ""
    style_guidance = ""

    # Warning callback for long context
    def warn_long_context(msg: str) -> None:
        console.print(warning(msg))

    if not no_taste:
        taste = storage.load_taste()
        if taste.strip():
            # Check if it's still the default template (not customized)
            if "Describe your aesthetic preferences" in taste and "Examples:" in taste:
                console.print(warning(
                    "Taste profile contains default template. "
                    "Run 'serendipity profile taste --edit' to customize it. Skipping for now."
                ))
            else:
                # Check taste length
                taste_words = storage.count_words(taste)
                if taste_words > 10000:
                    console.print(warning(
                        f"Taste profile is {taste_words:,} words (>10K). "
                        f"Consider condensing it for better results."
                    ))
                context_augmentation = f"<persistent_taste>\n{taste}\n</persistent_taste>"

    if config.history_enabled and not no_history:
        history_context = storage.build_history_context(warn_callback=warn_long_context)
        if history_context:
            if context_augmentation:
                context_augmentation += "\n\n" + history_context
            else:
                context_augmentation = history_context

    style_guidance = storage.build_style_guidance()

    # Check total context length
    total_context = context_augmentation + "\n\n" + context
    total_words = storage.count_words(total_context)
    if total_words > 10000:
        console.print(warning(
            f"Total context is {total_words:,} words (>10K). "
            f"This may impact quality or cost. Consider condensing."
        ))

    if verbose:
        console.print(Panel(
            f"Context length: {len(context)} chars\n"
            f"Model: {model}\n"
            f"Convergent: {n1}, Divergent: {n2}\n"
            f"History: {'enabled' if config.history_enabled and not no_history else 'disabled'}\n"
            f"Taste: {'included' if not no_taste and storage.load_taste().strip() else 'none'}\n"
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
        whorl=whorl,
        server_port=config.feedback_server_port,
        template_path=template_path,
        max_thinking_tokens=max_thinking_tokens,
    )

    console.print("[bold green]Discovering...[/bold green]")
    console.print()
    result = agent.run_sync(
        context,
        n1=n1,
        n2=n2,
        context_augmentation=context_augmentation,
        style_guidance=style_guidance,
    )
    console.print()

    # Save to history
    if config.history_enabled and not no_history:
        _save_to_history(storage, result)

    # Output based on format
    if output_format == "html":
        # Require Claude to have written the HTML file
        if not result.html_path or not result.html_path.exists():
            console.print(error("Claude failed to write HTML file"))
            console.print(f"[dim]Expected path: {agent.output_dir}[/dim]")
            raise typer.Exit(code=1)

        # Start feedback server with static file serving
        _start_feedback_server(
            storage,
            agent,
            config.feedback_server_port,
            static_dir=agent.output_dir,
            user_input=context,
            session_id=result.session_id,
        )

        # Open browser to the specific file
        import webbrowser
        filename = result.html_path.name
        url = f"http://localhost:{config.feedback_server_port}/{filename}"
        webbrowser.open(url)

        console.print(success(f"Opened in browser: {url}"))
        console.print(f"[dim]HTML file: {result.html_path}[/dim]")
        console.print(f"[dim]Feedback server running on localhost:{config.feedback_server_port}[/dim]")
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

    # Show cost and session info (for non-HTML output)
    if output_format != "html":
        if result.cost_usd:
            console.print(f"[dim]Cost: ${result.cost_usd:.4f}[/dim]")

        resume_cmd = agent.get_resume_command()
        if resume_cmd:
            console.print(f"[dim]Resume: {resume_cmd}[/dim]")


@app.command()
def config(
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Interactive configuration wizard",
    ),
    show: bool = typer.Option(
        False,
        "--show",
        help="Show current configuration",
    ),
    set_value: Optional[str] = typer.Option(
        None,
        "--set",
        help="Set a config value (key=value)",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        help="Reset configuration to defaults",
    ),
) -> None:
    """Manage serendipity configuration.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity config                  [dim]# Show config[/dim]
      [dim]$[/dim] serendipity config -i               [dim]# Interactive wizard[/dim]
      [dim]$[/dim] serendipity config --set model=haiku
      [dim]$[/dim] serendipity config --reset
    """
    storage = StorageManager()
    storage.ensure_dirs()

    if reset:
        cfg = storage.reset_config()
        console.print(success("Configuration reset to defaults"))
        return

    if set_value:
        # Parse key=value
        if "=" not in set_value:
            console.print(error("Invalid format. Use: --set key=value"))
            raise typer.Exit(code=1)

        key, value = set_value.split("=", 1)
        cfg = storage.load_config()

        # Type conversion based on key
        if key in ("history_enabled",):
            value = value.lower() in ("true", "1", "yes")
        elif key in ("max_recent_history", "feedback_server_port", "default_n1", "default_n2"):
            value = int(value)
        elif key == "max_thinking_tokens":
            value = int(value) if value.lower() not in ("null", "none", "") else None
        elif key == "html_style" and value.lower() == "null":
            value = None

        if hasattr(cfg, key):
            setattr(cfg, key, value)
            storage.save_config(cfg)
            console.print(success(f"Set {key} = {value}"))
        else:
            console.print(error(f"Unknown config key: {key}"))
            raise typer.Exit(code=1)
        return

    if interactive:
        cfg = storage.load_config()
        console.print(Panel(
            "Use ↑↓ to navigate, Enter to edit, 'Save & Exit' when done",
            title="Interactive Configuration",
            border_style="blue",
        ))

        while True:
            # Build choices showing current values
            choices = []
            cfg_dict = cfg.to_dict()

            for key, value in cfg_dict.items():
                display_val = str(value) if value is not None else "[auto]"
                if len(display_val) > 30:
                    display_val = display_val[:27] + "..."
                desc = CONFIG_DESCRIPTIONS.get(key, "")
                # Format: "setting_name: value  (description)"
                label = f"{key}: {display_val}"
                choices.append(questionary.Choice(title=label, value=key))

            choices.append(questionary.Choice(title="─" * 40, value=None, disabled=True))
            choices.append(questionary.Choice(title="💾 Save & Exit", value="__save__"))
            choices.append(questionary.Choice(title="❌ Cancel", value="__cancel__"))

            selected = questionary.select(
                "Select a setting to edit:",
                choices=choices,
                use_shortcuts=False,
                use_arrow_keys=True,
                instruction="(↑↓ navigate, Enter select)",
            ).ask()

            if selected is None or selected == "__cancel__":
                console.print(warning("Configuration cancelled"))
                return

            if selected == "__save__":
                storage.save_config(cfg)
                console.print(success("Configuration saved"))
                return

            # Edit the selected setting
            current_val = getattr(cfg, selected)
            desc = CONFIG_DESCRIPTIONS.get(selected, "")
            console.print(f"\n[dim]{desc}[/dim]")

            if selected == "default_model":
                new_val = questionary.select(
                    f"Select model:",
                    choices=["opus", "sonnet", "haiku"],
                    default=current_val,
                ).ask()
            elif selected in ("history_enabled",):
                new_val = questionary.confirm(
                    f"{selected}?",
                    default=current_val,
                ).ask()
            elif selected in ("max_recent_history", "feedback_server_port", "default_n1", "default_n2"):
                new_val = questionary.text(
                    f"Enter value:",
                    default=str(current_val),
                    validate=lambda x: x.isdigit() or "Must be a number",
                ).ask()
                if new_val:
                    new_val = int(new_val)
            elif selected == "html_style":
                new_val = questionary.text(
                    "Enter style (empty for auto):",
                    default=current_val or "",
                ).ask()
                if new_val == "":
                    new_val = None
            elif selected == "max_thinking_tokens":
                new_val = questionary.text(
                    "Enter token budget (empty to disable):",
                    default=str(current_val) if current_val else "",
                    validate=lambda x: x == "" or x.isdigit() or "Must be a number or empty",
                ).ask()
                if new_val == "" or new_val is None:
                    new_val = None
                else:
                    new_val = int(new_val)
            else:
                new_val = questionary.text(
                    f"Enter value:",
                    default=str(current_val) if current_val else "",
                ).ask()

            if new_val is not None:
                setattr(cfg, selected, new_val)
                console.print(success(f"Set {selected} = {new_val}"))
            console.print()  # Blank line before next menu

        return

    # Default: show config
    cfg = storage.load_config()
    table = Table(title="Configuration", show_lines=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")
    table.add_column("Description", style="dim")

    for key, value in cfg.to_dict().items():
        desc = CONFIG_DESCRIPTIONS.get(key, "")
        table.add_row(
            key,
            str(value) if value is not None else "[dim italic]auto[/dim italic]",
            desc,
        )

    console.print(table)
    console.print(f"\n[dim]Config file: {storage.config_path}[/dim]")


@profile_app.command()
def taste(
    show: bool = typer.Option(
        False,
        "--show",
        help="Show current taste profile",
    ),
    edit: bool = typer.Option(
        False,
        "--edit",
        help="Open taste.md in $EDITOR",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Clear taste profile",
    ),
) -> None:
    """Manage your taste profile.

    Your taste describes your aesthetic sensibilities, interests, and
    what kind of content you enjoy discovering.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile taste           [dim]# Show taste[/dim]
      [dim]$[/dim] serendipity profile taste --edit    [dim]# Edit in $EDITOR[/dim]
      [dim]$[/dim] serendipity profile taste --clear   [dim]# Clear taste[/dim]
    """
    storage = StorageManager()
    storage.ensure_dirs()

    taste_path = storage.get_taste_path()

    if clear:
        if not typer.confirm("Clear your taste profile? This cannot be undone."):
            console.print(warning("Cancelled"))
            return
        if taste_path.exists():
            taste_path.unlink()
        console.print(success("Taste profile cleared"))
        return

    if edit:
        # Create file if it doesn't exist
        if not taste_path.exists():
            taste_path.parent.mkdir(parents=True, exist_ok=True)
            taste_path.write_text(
                "# My Taste Profile\n\n"
                "<!-- DELETE EVERYTHING ABOVE AND BELOW THIS LINE -->\n"
                "<!-- Replace with your actual taste -->\n\n"
                "Describe your aesthetic preferences, interests, and what kind of content you enjoy.\n\n"
                "Examples:\n"
                "- I'm drawn to Japanese minimalism and wabi-sabi aesthetics\n"
                "- I love long-form essays on philosophy and design\n"
                "- I appreciate things that feel contemplative and unhurried\n\n"
                "<!-- This template will be skipped until you customize it -->\n"
            )

        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(taste_path)])
        console.print(success(f"Taste profile saved to {taste_path}"))
        return

    # Default: show taste
    taste_content = storage.load_taste()
    if taste_content.strip():
        console.print(Panel(taste_content, title="Taste Profile", border_style="blue"))
    else:
        console.print("[dim]No taste profile set. Run 'serendipity profile taste --edit' to create.[/dim]")
    console.print(f"\n[dim]Taste file: {taste_path}[/dim]")


@profile_app.command()
def history(
    show: bool = typer.Option(
        False,
        "--show",
        help="Show recommendation history",
    ),
    liked: bool = typer.Option(
        False,
        "--liked",
        help="Show only liked items",
    ),
    disliked: bool = typer.Option(
        False,
        "--disliked",
        help="Show only disliked items",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Clear all history",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Number of items to show",
    ),
) -> None:
    """View and manage recommendation history.

    History tracks all recommendations shown to you, including feedback
    (likes/dislikes) and whether learnings have been extracted.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile history                 [dim]# Show recent[/dim]
      [dim]$[/dim] serendipity profile history --liked         [dim]# Show liked only[/dim]
      [dim]$[/dim] serendipity profile history --clear         [dim]# Clear history[/dim]
    """
    storage = StorageManager()

    if clear:
        if typer.confirm("Are you sure you want to clear all history?"):
            storage.clear_history()
            console.print(success("History cleared"))
        return

    # Get entries
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


@profile_app.command()
def learnings(
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Interactive learning extraction wizard",
    ),
    show: bool = typer.Option(
        False,
        "--show",
        help="Show current learnings",
    ),
    edit: bool = typer.Option(
        False,
        "--edit",
        help="Open learnings.md in $EDITOR",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Clear all learnings",
    ),
) -> None:
    """Manage learnings extracted from your likes/dislikes.

    Learnings compress patterns from your feedback into concise preferences
    that guide future recommendations more efficiently.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile learnings           [dim]# Show learnings[/dim]
      [dim]$[/dim] serendipity profile learnings -i        [dim]# Interactive wizard[/dim]
      [dim]$[/dim] serendipity profile learnings --edit    [dim]# Edit in $EDITOR[/dim]
    """
    storage = StorageManager()
    storage.ensure_dirs()

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
        console.print("[dim]No learnings yet. Run 'serendipity profile learnings -i' to extract from history.[/dim]")
    console.print(f"\n[dim]Learnings file: {storage.learnings_path}[/dim]")


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


def cli() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    cli()
