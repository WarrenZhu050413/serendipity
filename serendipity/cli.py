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
    "preferences_path": "Path to your taste profile (markdown file with your preferences)",
    "template_path": "Path to HTML template (copied from package default on first use)",
    "history_enabled": "Track recommendations to avoid repeats and learn from feedback",
    "max_recent_history": "Number of recent items to include in context (avoids repeating)",
    "feedback_server_port": "Port for the HTML feedback server (localhost)",
    "default_model": "Claude model to use (haiku=fast, sonnet=balanced, opus=best)",
    "default_n1": "Default number of convergent recommendations (more of what you like)",
    "default_n2": "Default number of divergent recommendations (expand your taste)",
    "html_style": "HTML styling preference (null=auto-generate based on taste)",
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

# Context subcommand group for managing what gets injected into Claude
context_app = typer.Typer(
    name="context",
    help="View and manage the context injected into Claude's prompt",
    rich_markup_mode="rich",
    invoke_without_command=True,
)
app.add_typer(context_app, name="context")

console = Console()


@app.callback()
def callback(ctx: typer.Context) -> None:
    """Personal Serendipity Engine - discover convergent and divergent content recommendations."""
    # If no subcommand was invoked, show help
    if ctx.invoked_subcommand is None:
        # Show usage panel instead of full help
        console.print(Panel(
            "[bold]Commands:[/bold]\n\n"
            "  serendipity discover context.md   # Run discovery\n"
            "  serendipity config                # Manage configuration\n"
            "  serendipity context               # View/manage what Claude sees\n\n"
            "[bold]Quick usage:[/bold]\n\n"
            "  serendipity discover context.md   # From file\n"
            "  serendipity discover -p           # From clipboard\n"
            "  serendipity discover -i           # Open editor\n",
            title="serendipity",
            border_style="blue",
        ))


@context_app.callback()
def context_callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show word counts per section",
    ),
) -> None:
    """Preview what context gets injected into Claude's prompt.

    Shows preferences, rules, recent history, and pending feedback.
    """
    if ctx.invoked_subcommand is not None:
        return

    storage = StorageManager()
    storage.ensure_dirs()

    output_lines = []

    # Preferences section
    preferences = storage.load_preferences()
    if preferences.strip():
        # Check if it's still the default template
        if "Describe your aesthetic preferences" in preferences and "Examples:" in preferences:
            pref_display = "[dim]Default template (not customized)[/dim]"
            pref_words = 0
        else:
            pref_words = storage.count_words(preferences)
            pref_display = preferences[:500] + "..." if len(preferences) > 500 else preferences
    else:
        pref_display = "[dim]Not set[/dim]"
        pref_words = 0

    header = "PREFERENCES" + (f" ({pref_words} words)" if verbose and pref_words else "")
    output_lines.append(f"[bold cyan]{header}[/bold cyan]")
    output_lines.append(pref_display)
    output_lines.append("")

    # Rules section
    rules_content = storage.load_rules()
    if rules_content.strip():
        rules_words = storage.count_words(rules_content)
        rules_display = rules_content[:500] + "..." if len(rules_content) > 500 else rules_content
    else:
        rules_display = "[dim]No rules defined[/dim]"
        rules_words = 0

    header = "DISCOVERY RULES" + (f" ({rules_words} words)" if verbose and rules_words else "")
    output_lines.append(f"[bold cyan]{header}[/bold cyan]")
    output_lines.append(rules_display)
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
        total_words = pref_words + rules_words
        output_lines.append("")
        output_lines.append(f"[dim]Total context: ~{total_words} words (excluding history)[/dim]")

    console.print(Panel(
        "\n".join(output_lines),
        title="Model Context Preview",
        border_style="blue",
    ))

    console.print("\n[bold]Subcommands:[/bold]")
    console.print("  serendipity context preferences   # Edit taste profile")
    console.print("  serendipity context history       # View history")
    console.print("  serendipity context rules         # Manage rules")


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
) -> str:
    """Get context from various sources using priority waterfall.

    Priority:
    1. Explicit file argument
    2. -p flag (clipboard)
    3. -i flag (editor)
    4. Stdin (if piped)
    5. Error
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

    # 5. No input - show help
    console.print(Panel(
        "[bold]Usage:[/bold]\n\n"
        "  serendipity context.md          # From file\n"
        "  serendipity -                   # From stdin\n"
        "  serendipity -p                  # From clipboard\n"
        "  serendipity -i                  # Open editor\n"
        "  cat notes.md | serendipity      # Piped stdin\n",
        title="serendipity",
        border_style="blue",
    ))
    raise typer.Exit(code=0)


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
    no_preferences: bool = typer.Option(
        False,
        "--no-preferences",
        help="Don't include preferences.md for this run",
    ),
    whorl: bool = typer.Option(
        False,
        "--whorl",
        "-w",
        help="Enable Whorl integration (search personal knowledge base for context)",
    ),
) -> None:
    """Discover convergent and divergent content recommendations.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity discover context.md       [dim]# From file[/dim]
      [dim]$[/dim] serendipity discover -                [dim]# From stdin[/dim]
      [dim]$[/dim] serendipity discover -p               [dim]# From clipboard[/dim]
      [dim]$[/dim] serendipity discover -i               [dim]# Open editor[/dim]
      [dim]$[/dim] serendipity discover context.md --n1 3 --n2 8
      [dim]$[/dim] serendipity discover context.md -o terminal  [dim]# No browser[/dim]
      [dim]$[/dim] serendipity discover context.md -w    [dim]# With Whorl knowledge base[/dim]
    """
    # Load storage and config
    storage = StorageManager()
    storage.ensure_dirs()
    config = storage.load_config()

    # Use config defaults if not specified
    if model is None:
        model = config.default_model
    if n1 is None:
        n1 = config.default_n1
    if n2 is None:
        n2 = config.default_n2

    # Get context from input sources
    context = _get_context(file_path, paste, interactive)

    # Build context augmentation
    context_augmentation = ""
    style_guidance = ""

    # Warning callback for long context
    def warn_long_context(msg: str) -> None:
        console.print(warning(msg))

    if not no_preferences:
        preferences = storage.load_preferences()
        if preferences.strip():
            # Check if it's still the default template (not customized)
            if "Describe your aesthetic preferences" in preferences and "Examples:" in preferences:
                console.print(warning(
                    "Preferences file contains default template. "
                    "Run 'serendipity context preferences' to customize it. Skipping for now."
                ))
            else:
                # Check preferences length
                pref_words = storage.count_words(preferences)
                if pref_words > 10000:
                    console.print(warning(
                        f"Preferences file is {pref_words:,} words (>10K). "
                        f"Consider condensing it for better results."
                    ))
                context_augmentation = f"<persistent_preferences>\n{preferences}\n</persistent_preferences>"

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
            f"Preferences: {'included' if not no_preferences and storage.load_preferences().strip() else 'none'}",
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
            elif selected in ("history_enabled", "summarize_old_history"):
                new_val = questionary.confirm(
                    f"{selected}?",
                    default=current_val,
                ).ask()
            elif selected in ("max_recent_history", "summary_threshold", "feedback_server_port", "default_n1", "default_n2"):
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


@context_app.command()
def preferences(
    show: bool = typer.Option(
        False,
        "--show",
        help="Show current preferences",
    ),
    edit: bool = typer.Option(
        False,
        "--edit",
        help="Open preferences.md in $EDITOR",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Clear all preferences",
    ),
) -> None:
    """Manage your persistent taste profile.

    Your preferences describe your aesthetic sensibilities, interests, and
    what kind of content you enjoy discovering.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity context preferences           [dim]# Show preferences[/dim]
      [dim]$[/dim] serendipity context preferences --edit    [dim]# Edit in $EDITOR[/dim]
      [dim]$[/dim] serendipity context preferences --clear   [dim]# Clear preferences[/dim]
    """
    storage = StorageManager()
    storage.ensure_dirs()

    prefs_path = storage.get_preferences_path()

    if clear:
        if not typer.confirm("Clear all preferences? This cannot be undone."):
            console.print(warning("Cancelled"))
            return
        if prefs_path.exists():
            prefs_path.unlink()
        console.print(success("Preferences cleared"))
        return

    if edit:
        # Create file if it doesn't exist
        if not prefs_path.exists():
            prefs_path.parent.mkdir(parents=True, exist_ok=True)
            prefs_path.write_text(
                "# My Taste Profile\n\n"
                "<!-- DELETE EVERYTHING ABOVE AND BELOW THIS LINE -->\n"
                "<!-- Replace with your actual preferences -->\n\n"
                "Describe your aesthetic preferences, interests, and what kind of content you enjoy.\n\n"
                "Examples:\n"
                "- I'm drawn to Japanese minimalism and wabi-sabi aesthetics\n"
                "- I love long-form essays on philosophy and design\n"
                "- I appreciate things that feel contemplative and unhurried\n\n"
                "<!-- This template will be skipped until you customize it -->\n"
            )

        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(prefs_path)])
        console.print(success(f"Preferences saved to {prefs_path}"))
        return

    # Default: show preferences
    prefs = storage.load_preferences()
    if prefs.strip():
        console.print(Panel(prefs, title="Preferences", border_style="blue"))
    else:
        console.print("[dim]No preferences set. Run 'serendipity context preferences --edit' to create.[/dim]")
    console.print(f"\n[dim]Preferences file: {prefs_path}[/dim]")


@context_app.command()
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
    (likes/dislikes) and whether rules have been extracted.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity context history                 [dim]# Show recent[/dim]
      [dim]$[/dim] serendipity context history --liked         [dim]# Show liked only[/dim]
      [dim]$[/dim] serendipity context history --clear         [dim]# Clear history[/dim]
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


@context_app.command()
def rules(
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Interactive rule extraction wizard",
    ),
    show: bool = typer.Option(
        False,
        "--show",
        help="Show current rules",
    ),
    edit: bool = typer.Option(
        False,
        "--edit",
        help="Open rules.md in $EDITOR",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Clear all rules",
    ),
) -> None:
    """Manage discovery rules extracted from likes/dislikes.

    Rules compress patterns from your feedback into concise preferences
    that guide future recommendations more efficiently.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity context rules           [dim]# Show rules[/dim]
      [dim]$[/dim] serendipity context rules -i        [dim]# Interactive wizard[/dim]
      [dim]$[/dim] serendipity context rules --edit    [dim]# Edit in $EDITOR[/dim]
    """
    storage = StorageManager()
    storage.ensure_dirs()

    if clear:
        if not typer.confirm("Clear all rules? This cannot be undone."):
            console.print(warning("Cancelled"))
            return
        storage.clear_rules()
        console.print(success("Rules cleared"))
        return

    if edit:
        rules_path = storage.rules_path
        if not rules_path.exists():
            rules_path.write_text("# My Discovery Rules\n\n## Likes\n\n## Dislikes\n")
        editor = os.environ.get("EDITOR", "vim")
        subprocess.run([editor, str(rules_path)])
        console.print(success(f"Rules saved to {rules_path}"))
        return

    if interactive:
        _rules_interactive_wizard(storage)
        return

    # Default: show rules
    rules_content = storage.load_rules()
    if rules_content.strip():
        console.print(Panel(rules_content, title="Discovery Rules", border_style="blue"))
    else:
        console.print("[dim]No rules defined yet. Run 'serendipity context rules -i' to extract from history.[/dim]")
    console.print(f"\n[dim]Rules file: {storage.rules_path}[/dim]")


def _rules_interactive_wizard(storage: StorageManager) -> None:
    """Interactive wizard for rule extraction."""
    from serendipity.search import HistorySearcher

    console.print(Panel(
        "Extract patterns from your likes/dislikes into reusable rules",
        title="Rule Extraction Wizard",
        border_style="blue",
    ))

    # Step 1: Choose workflow
    workflow = questionary.select(
        "What would you like to do?",
        choices=[
            questionary.Choice(
                "Extract rules from likes/dislikes (Claude proposes)",
                value="extract",
            ),
            questionary.Choice(
                "Write a rule and auto-tag matching items",
                value="write",
            ),
            questionary.Choice(
                "View/edit existing rules",
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
        rules_content = storage.load_rules()
        if rules_content.strip():
            console.print(Panel(rules_content, title="Current Rules", border_style="blue"))
        else:
            console.print("[dim]No rules yet.[/dim]")
        if questionary.confirm("Edit rules in $EDITOR?", default=False).ask():
            editor = os.environ.get("EDITOR", "vim")
            if not storage.rules_path.exists():
                storage.rules_path.write_text("# My Discovery Rules\n\n## Likes\n\n## Dislikes\n")
            subprocess.run([editor, str(storage.rules_path)])
        return

    if workflow == "extract":
        _extract_rule_workflow(storage)
    elif workflow == "write":
        _write_rule_workflow(storage)


def _extract_rule_workflow(storage: StorageManager) -> None:
    """Workflow: Claude proposes rules from selected items."""
    from serendipity.rules import generate_rule
    from serendipity.search import HistorySearcher

    # Step 2: Choose feedback type
    unextracted_liked = storage.get_unextracted_entries("liked")
    unextracted_disliked = storage.get_unextracted_entries("disliked")

    if not unextracted_liked and not unextracted_disliked:
        console.print(warning("No unextracted items found. All your likes/dislikes are already in rules."))
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

    # Step 4: Generate rule with Claude
    console.print(info(f"Generating rule from {len(selected)} items..."))

    try:
        rule = asyncio.run(generate_rule(selected, feedback_type))
    except Exception as e:
        console.print(error(f"Failed to generate rule: {e}"))
        return

    if not rule:
        console.print(error("Failed to generate rule. Try selecting different items."))
        return

    # Step 5: Show and confirm
    console.print()
    console.print(Panel(
        f"### {rule.title}\n{rule.content}",
        title="Proposed Rule",
        border_style="green",
    ))

    action = questionary.select(
        "Accept this rule?",
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
        edited_title = questionary.text("Rule title:", default=rule.title).ask()
        edited_content = questionary.text("Rule content:", default=rule.content).ask()
        if edited_title and edited_content:
            rule.title = edited_title
            rule.content = edited_content

    # Save rule and mark items as extracted
    storage.append_rule(rule.title, rule.content, rule.rule_type)
    urls = [e.url for e in selected]
    count = storage.mark_extracted(urls)

    console.print(success(f"Rule saved to {storage.rules_path}"))
    console.print(success(f"Marked {count} items as extracted"))


def _write_rule_workflow(storage: StorageManager) -> None:
    """Workflow: User writes rule, Claude finds matching items."""
    from serendipity.rules import find_matching_items

    # Step 1: Get rule type
    rule_type = questionary.select(
        "What type of rule?",
        choices=[
            questionary.Choice("Like (things I enjoy)", value="like"),
            questionary.Choice("Dislike (things to avoid)", value="dislike"),
        ],
    ).ask()

    if rule_type is None:
        console.print(warning("Cancelled"))
        return

    # Step 2: Get rule text
    console.print("\n[dim]Write a description of the pattern (can be a few sentences):[/dim]")
    rule_text = questionary.text(
        "Rule:",
        multiline=False,
    ).ask()

    if not rule_text or not rule_text.strip():
        console.print(warning("Cancelled"))
        return

    # Step 3: Find matching items
    feedback = "liked" if rule_type == "like" else "disliked"
    entries = storage.get_unextracted_entries(feedback)

    if not entries:
        console.print(warning(f"No unextracted {feedback} items to match against."))
        # Still save the rule
        title = questionary.text("Rule title (short):", default="").ask()
        if title:
            storage.append_rule(title, rule_text.strip(), rule_type)
            console.print(success("Rule saved (no items to mark as extracted)"))
        return

    console.print(info(f"Finding matching items among {len(entries)} {feedback} entries..."))

    try:
        matching_urls = asyncio.run(find_matching_items(rule_text, entries))
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
                questionary.Choice("No, save rule without marking", value="no"),
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
        "Rule title (short):",
        default="",
    ).ask()

    if not title:
        console.print(warning("Cancelled - no title provided"))
        return

    storage.append_rule(title, rule_text.strip(), rule_type)
    console.print(success(f"Rule saved to {storage.rules_path}"))

    if mark_items and matching_urls:
        count = storage.mark_extracted(matching_urls)
        console.print(success(f"Marked {count} items as extracted"))


def cli() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    cli()
