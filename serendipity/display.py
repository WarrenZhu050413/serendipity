"""Rich display utilities for serendipity output visualization."""

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax


@dataclass
class DisplayConfig:
    """Configuration for output display."""

    verbose: bool = False


@dataclass
class AgentDisplay:
    """Handles display of agent messages during streaming."""

    console: Console
    config: DisplayConfig
    _pending_tool_use: dict[str, dict] = field(default_factory=dict)

    def show_thinking(self, thinking: str) -> None:
        """Display thinking block (only in verbose mode)."""
        if not self.config.verbose:
            return

        # Truncate very long thinking blocks
        display_text = thinking
        if len(thinking) > 500:
            display_text = thinking[:500] + "..."

        self.console.print()
        self.console.print(
            Panel(
                f"[dim]{display_text}[/dim]",
                title="[dim]💭 Thinking[/dim]",
                border_style="dim",
            )
        )

    def show_tool_use(self, name: str, tool_id: str, input_data: dict) -> None:
        """Display tool use request.

        In verbose mode: Full panel with JSON input
        In normal mode: Compact one-liner
        """
        self._pending_tool_use[tool_id] = {"name": name, "input": input_data}

        if self.config.verbose:
            # Full panel with input JSON
            input_json = json.dumps(input_data, indent=2, default=str)
            self.console.print()
            self.console.print(
                Panel(
                    Syntax(input_json, "json", theme="monokai", word_wrap=True),
                    title=f"[cyan]🔧 {name}[/cyan]",
                    subtitle="[dim]Input[/dim]",
                    border_style="cyan",
                )
            )
        else:
            # Compact one-liner
            input_summary = self._summarize_input(name, input_data)
            self.console.print(f"[cyan]🔧 {name}[/cyan]{input_summary}")

    def show_tool_result(
        self, tool_use_id: str, content: Any, is_error: Optional[bool]
    ) -> None:
        """Display tool result (verbose mode only shows full result)."""
        is_error = is_error or False
        tool_info = self._pending_tool_use.get(tool_use_id, {})
        name = tool_info.get("name", "")

        if self.config.verbose:
            # Full panel with output JSON
            output_str = self._format_content(content)
            style = "red" if is_error else "green"
            title = "❌ Error" if is_error else "✓ Result"
            self.console.print(
                Panel(
                    Syntax(output_str, "json", theme="monokai", word_wrap=True),
                    title=f"[{style}]{title}[/{style}]",
                    border_style=style,
                )
            )

    def show_text(self, text: str) -> None:
        """Display text block (verbose mode shows streamed text output)."""
        if not text.strip():
            return

        if self.config.verbose:
            self.console.print(text, end="", highlight=False)

    def _summarize_input(self, tool_name: str, input_data: dict) -> str:
        """Create compact input summary for normal mode."""
        if tool_name == "WebFetch":
            url = input_data.get("url", "")
            if url:
                # Truncate long URLs
                display_url = url if len(url) < 60 else url[:57] + "..."
                return f" [dim]{display_url}[/dim]"
            return ""

        elif tool_name == "WebSearch":
            query = input_data.get("query", "")
            if query:
                return f' [dim]"{query}"[/dim]'
            return ""

        else:
            # Generic: show first key-value if short
            if input_data:
                first_key = list(input_data.keys())[0]
                first_val = str(input_data[first_key])[:40]
                return f" [dim]{first_key}={first_val}[/dim]"
            return ""

    def _format_content(self, content: Any) -> str:
        """Format content for verbose JSON display."""
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
                return json.dumps(parsed, indent=2, default=str)
            except (json.JSONDecodeError, TypeError):
                return content

        if isinstance(content, dict):
            return json.dumps(content, indent=2, default=str)

        return str(content)
