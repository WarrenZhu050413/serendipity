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
from serendipity.config.types import TypesConfig
from serendipity.context_sources import ContextSourceManager
from serendipity.prompts.builder import PromptBuilder
from serendipity.resources import get_base_template

from serendipity.storage import HistoryEntry, StorageManager

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
) -> None:
    """View your profile - what Claude knows about you.

    Shows all enabled context sources: taste, learnings, history, etc.

    [bold cyan]EXAMPLES[/bold cyan]:
      [dim]$[/dim] serendipity profile             [dim]# Overview of all sources[/dim]
      [dim]$[/dim] serendipity profile --show      [dim]# Full content of each source[/dim]
      [dim]$[/dim] serendipity profile --edit      [dim]# Edit taste.md[/dim]
    """
    storage = StorageManager()
    storage.ensure_dirs()

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
    settings = TypesConfig.from_yaml(storage.settings_path)

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
    console.print(f"\n[dim]Edit taste: serendipity profile --edit[/dim]")
    console.print(f"[dim]Full content: serendipity profile --show[/dim]")
    console.print(f"[dim]Manage sources: serendipity settings[/dim]")


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
    settings = TypesConfig.from_yaml(storage.settings_path)

    # Use settings defaults if not specified
    if model is None:
        model = settings.model
    # Use CLI thinking value (extended thinking is CLI-only now)
    max_thinking_tokens = thinking

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
            f"Total count: {settings.total_count}\n"
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
        server_port=settings.feedback_server_port,
        template_path=template_path,
        max_thinking_tokens=max_thinking_tokens,
        types_config=settings,
    )

    console.print("[bold green]Discovering...[/bold green]")
    console.print()
    result = agent.run_sync(
        context,
        context_augmentation=context_augmentation,
        style_guidance=style_guidance,
    )
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
            settings.feedback_server_port,
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
        if actual_port != settings.feedback_server_port:
            console.print(f"[yellow]Port {settings.feedback_server_port} was in use, using port {actual_port}[/yellow]")
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

    # Show cost and session info (for non-HTML output)
    if output_format != "html":
        if result.cost_usd:
            console.print(f"[dim]Cost: ${result.cost_usd:.4f}[/dim]")

        resume_cmd = agent.get_resume_command()
        if resume_cmd:
            console.print(f"[dim]Resume: {resume_cmd}[/dim]")


@app.command()
def settings(
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
    $ serendipity settings --edit                 # Edit in $EDITOR
    $ serendipity settings --reset                # Restore defaults
    $ serendipity settings --enable-source whorl  # Enable context source
    """
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

    if preview:
        # Show the prompt that would be generated
        config = TypesConfig.from_yaml(settings_path)
        builder = PromptBuilder(config)
        console.print(Panel(
            builder.build_type_guidance(),
            title="Generated Prompt Sections",
            border_style="dim",
        ))
        return

    # Handle enable/disable source
    if enable_source or disable_source:
        config = TypesConfig.from_yaml(settings_path)

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
    config = TypesConfig.from_yaml(settings_path)

    # Show top-level settings
    console.print("\n[bold]Settings[/bold]")
    console.print(f"  model: [cyan]{config.model}[/cyan]")
    console.print(f"  total_count: [cyan]{config.total_count}[/cyan]")
    console.print(f"  feedback_server_port: [cyan]{config.feedback_server_port}[/cyan]")

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

    if settings_path.exists():
        console.print(f"\n[dim]Config: {settings_path}[/dim]")
    else:
        console.print(f"\n[dim]Using defaults. Run 'serendipity settings --edit' to customize.[/dim]")


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

    taste_path = storage.taste_path

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
