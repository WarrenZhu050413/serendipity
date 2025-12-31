"""Claude Agent for serendipity discovery."""

import asyncio
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
import structlog
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from rich.console import Console

from serendipity.display import AgentDisplay, DisplayConfig

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer() if sys.stdout.isatty()
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()

PROMPT_TEMPLATE = Path(__file__).parent / "prompt.txt"
WHORL_PLUGIN_PATH = Path(__file__).parent / "plugins" / "whorl"
WHORL_PORT = 8081
WHORL_LOG_PATH = Path.home() / ".whorl" / "server.log"


def check_whorl_setup(console: Console) -> tuple[bool, str]:
    """Check if whorl is properly set up.

    Args:
        console: Rich console for output

    Returns:
        Tuple of (is_ready, error_message)
    """
    import shutil

    # Check 1: Is whorl CLI installed?
    if not shutil.which("whorl"):
        return False, (
            "[red]Whorl not installed.[/red]\n\n"
            "To use whorl integration, install it first:\n"
            "  [cyan]pip install whorled[/cyan]\n"
            "  [cyan]whorl init[/cyan]\n\n"
            "Then add documents to [cyan]~/.whorl/docs/[/cyan]"
        )

    # Check 2: Is whorl initialized?
    whorl_home = Path.home() / ".whorl"
    if not whorl_home.exists():
        return False, (
            "[red]Whorl not initialized.[/red]\n\n"
            "Run the following to set up whorl:\n"
            "  [cyan]whorl init[/cyan]\n\n"
            "Then add documents to [cyan]~/.whorl/docs/[/cyan]"
        )

    # Check 3: Are there any documents?
    docs_dir = whorl_home / "docs"
    if not docs_dir.exists() or not any(docs_dir.iterdir()):
        return False, (
            "[yellow]Whorl has no documents.[/yellow]\n\n"
            "Add documents to your knowledge base:\n"
            "  [cyan]whorl upload ~/notes[/cyan]  # Upload a folder\n"
            "  Or copy files to [cyan]~/.whorl/docs/[/cyan]\n\n"
            "Continuing without whorl integration..."
        )

    return True, ""


def ensure_whorl_running(console: Console) -> bool:
    """Ensure the whorl server is running.

    Args:
        console: Rich console for output

    Returns:
        True if whorl is running, False if failed to start
    """
    # First check if whorl is properly set up
    is_ready, error_msg = check_whorl_setup(console)
    if not is_ready:
        console.print(error_msg)
        # If it's just empty docs, we can still try to run
        if "no documents" not in error_msg.lower():
            return False

    # Check if whorl is already running
    try:
        response = httpx.get(f"http://localhost:{WHORL_PORT}/health", timeout=2.0)
        if response.status_code == 200:
            console.print(f"[dim]Whorl server already running on port {WHORL_PORT}[/dim]")
            return True
    except httpx.RequestError:
        pass

    # Try to start whorl server
    console.print(f"[yellow]Starting whorl server on port {WHORL_PORT}...[/yellow]")
    try:
        WHORL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(WHORL_LOG_PATH, "a") as log_file:
            subprocess.Popen(
                ["whorl", "server", "--port", str(WHORL_PORT)],
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
            )

        # Wait for server to start
        for _ in range(10):
            time.sleep(0.5)
            try:
                response = httpx.get(f"http://localhost:{WHORL_PORT}/health", timeout=2.0)
                if response.status_code == 200:
                    console.print(f"[green]Whorl server started on port {WHORL_PORT}[/green]")
                    return True
            except httpx.RequestError:
                continue

        console.print(f"[red]Failed to start whorl server. Check {WHORL_LOG_PATH}[/red]")
        return False

    except FileNotFoundError:
        console.print("[red]whorl command not found. Install with: pip install whorled[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Failed to start whorl: {e}[/red]")
        return False


@dataclass
class Recommendation:
    """A single recommendation."""

    url: str
    reason: str


@dataclass
class HtmlStyle:
    """HTML styling generated by Claude."""

    description: str
    css: str


@dataclass
class DiscoveryResult:
    """Result from a discovery operation."""

    convergent: list[Recommendation]
    divergent: list[Recommendation]
    session_id: str
    cost_usd: Optional[float] = None
    raw_response: Optional[str] = None
    html_style: Optional[HtmlStyle] = None


class SerendipityAgent:
    """Claude agent for serendipity discovery."""

    def __init__(
        self,
        console: Optional[Console] = None,
        model: str = "opus",
        verbose: bool = False,
        whorl: bool = False,
    ):
        """Initialize the Serendipity agent.

        Args:
            console: Rich console for output
            model: Claude model to use (haiku, sonnet, opus)
            verbose: Show detailed progress
            whorl: Enable whorl integration for personalized context
        """
        self.console = console or Console()
        self.model = model
        self.verbose = verbose
        self.whorl = whorl
        self.prompt_template = PROMPT_TEMPLATE.read_text()
        self.last_session_id: Optional[str] = None
        self.cost_usd: Optional[float] = None

        # Initialize whorl if enabled
        if self.whorl:
            if not ensure_whorl_running(self.console):
                self.console.print("[yellow]Continuing without whorl integration[/yellow]")
                self.whorl = False

    def _get_plugins(self) -> list[dict]:
        """Get plugin configurations.

        Returns:
            List of plugin configs for ClaudeAgentOptions
        """
        plugins = []
        if self.whorl:
            plugins.append({"type": "local", "path": str(WHORL_PLUGIN_PATH)})
        return plugins

    async def discover(
        self,
        context: str,
        n1: int = 5,
        n2: int = 5,
        context_augmentation: str = "",
        style_guidance: str = "",
    ) -> DiscoveryResult:
        """Run discovery on user context.

        Args:
            context: User's context (text, links, instructions)
            n1: Number of convergent recommendations
            n2: Number of divergent recommendations
            context_augmentation: Additional context (preferences, history)
            style_guidance: Style guidance for HTML output

        Returns:
            DiscoveryResult with recommendations
        """
        # Build full context
        full_context_parts = []
        if context_augmentation:
            full_context_parts.append(context_augmentation)
        full_context_parts.append(f"<current_context>\n{context}\n</current_context>")
        if style_guidance:
            full_context_parts.append(style_guidance)

        full_context = "\n\n".join(full_context_parts)

        prompt = self.prompt_template.format(
            user_context=full_context,
            n1=n1,
            n2=n2,
        )

        # Build allowed tools list
        allowed_tools = ["WebFetch", "WebSearch"]

        # Add whorl MCP tools if enabled
        if self.whorl:
            allowed_tools.extend([
                "mcp__whorl__text_search_text_search_post",
                "mcp__whorl__agent_search_agent_search_post",
                "mcp__whorl__ingest_ingest_post",
                "mcp__whorl__bash_bash_post",
            ])

        # Build options with plugins if whorl is enabled
        plugins = self._get_plugins()
        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt="You are a discovery engine." + (
                " You have access to the user's personal knowledge base via whorl. "
                "Search it FIRST to understand their preferences and interests before making recommendations."
                if self.whorl else ""
            ),
            max_turns=50 if self.whorl else 20,  # More turns for whorl searches
            allowed_tools=allowed_tools,
            plugins=plugins if plugins else None,
        )

        response_text = []
        session_id = ""
        cost_usd = None

        # Set up display for streaming output
        display = AgentDisplay(
            console=self.console,
            config=DisplayConfig(verbose=self.verbose),
        )

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for msg in client.receive_response():
                # Log system init message for debugging plugins/MCP
                if isinstance(msg, SystemMessage) and msg.subtype == "init":
                    data = msg.data
                    loaded_plugins = data.get("plugins", [])
                    slash_commands = data.get("slash_commands", [])
                    mcp_servers = data.get("mcp_servers", [])

                    logger.info(
                        "SDK initialized",
                        plugins=[p.get("name") for p in loaded_plugins] if loaded_plugins else [],
                        slash_commands=slash_commands,
                        mcp_servers=mcp_servers,
                        whorl_enabled=self.whorl,
                    )

                    if self.verbose and loaded_plugins:
                        self.console.print(f"[dim]Loaded plugins: {[p.get('name') for p in loaded_plugins]}[/dim]")
                        if mcp_servers:
                            self.console.print(f"[dim]MCP servers: {mcp_servers}[/dim]")

                elif isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ThinkingBlock):
                            display.show_thinking(block.thinking)

                        elif isinstance(block, ToolUseBlock):
                            display.show_tool_use(
                                name=block.name,
                                tool_id=block.id,
                                input_data=block.input or {},
                            )

                        elif isinstance(block, ToolResultBlock):
                            display.show_tool_result(
                                tool_use_id=block.tool_use_id,
                                content=block.content,
                                is_error=block.is_error,
                            )

                        elif isinstance(block, TextBlock):
                            response_text.append(block.text)
                            display.show_text(block.text)

                elif isinstance(msg, ResultMessage):
                    session_id = msg.session_id
                    cost_usd = msg.total_cost_usd

        self.last_session_id = session_id
        self.cost_usd = cost_usd

        # Parse JSON from response
        full_response = "".join(response_text)
        parsed = self._parse_json(full_response)

        # Extract html_style if present
        html_style = None
        if "html_style" in parsed:
            style_data = parsed["html_style"]
            if isinstance(style_data, dict):
                html_style = HtmlStyle(
                    description=style_data.get("description", ""),
                    css=style_data.get("css", ""),
                )

        return DiscoveryResult(
            convergent=[
                Recommendation(url=r.get("url", ""), reason=r.get("reason", ""))
                for r in parsed.get("convergent", [])
            ],
            divergent=[
                Recommendation(url=r.get("url", ""), reason=r.get("reason", ""))
                for r in parsed.get("divergent", [])
            ],
            session_id=session_id,
            cost_usd=cost_usd,
            raw_response=full_response,
            html_style=html_style,
        )

    async def get_more(
        self,
        session_id: str,
        rec_type: str,
        count: int = 5,
    ) -> list[Recommendation]:
        """Get more recommendations by resuming a session.

        Args:
            session_id: Session ID to resume
            rec_type: Type of recommendations ("convergent" or "divergent")
            count: Number of additional recommendations

        Returns:
            List of new recommendations
        """
        type_description = (
            "convergent (matching their taste directly)"
            if rec_type == "convergent"
            else "divergent (expanding their palette)"
        )

        prompt = f"""Give me {count} more {type_description} recommendations, different from what you've already suggested.

Output as JSON:
{{
  "{rec_type}": [{{"url": "...", "reason": "..."}}]
}}"""

        # Build allowed tools list
        allowed_tools = ["WebFetch", "WebSearch"]
        if self.whorl:
            allowed_tools.extend([
                "mcp__whorl__text_search_text_search_post",
                "mcp__whorl__agent_search_agent_search_post",
                "mcp__whorl__ingest_ingest_post",
                "mcp__whorl__bash_bash_post",
            ])

        plugins = self._get_plugins()
        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt="You are a discovery engine.",
            max_turns=50 if self.whorl else 10,
            allowed_tools=allowed_tools,
            plugins=plugins if plugins else None,
            resume=session_id,  # Resume the previous session
        )

        response_text = []
        new_session_id = ""
        cost_usd = None

        # Set up display for streaming output
        display = AgentDisplay(
            console=self.console,
            config=DisplayConfig(verbose=self.verbose),
        )

        logger.info(
            "get_more starting",
            session_id=session_id,
            rec_type=rec_type,
            count=count,
            whorl_enabled=self.whorl,
        )

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for msg in client.receive_response():
                # Log system init message for debugging plugins/MCP
                if isinstance(msg, SystemMessage) and msg.subtype == "init":
                    data = msg.data
                    logger.info(
                        "SDK resumed",
                        plugins=[p.get("name") for p in data.get("plugins", [])],
                        mcp_servers=data.get("mcp_servers", []),
                    )

                elif isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, ThinkingBlock):
                            display.show_thinking(block.thinking)

                        elif isinstance(block, ToolUseBlock):
                            display.show_tool_use(
                                name=block.name,
                                tool_id=block.id,
                                input_data=block.input or {},
                            )

                        elif isinstance(block, ToolResultBlock):
                            display.show_tool_result(
                                tool_use_id=block.tool_use_id,
                                content=block.content,
                                is_error=block.is_error,
                            )

                        elif isinstance(block, TextBlock):
                            response_text.append(block.text)
                            display.show_text(block.text)

                elif isinstance(msg, ResultMessage):
                    new_session_id = msg.session_id
                    cost_usd = msg.total_cost_usd

        # Update session and cost
        self.last_session_id = new_session_id
        if cost_usd:
            self.cost_usd = (self.cost_usd or 0) + cost_usd

        # Parse JSON from response
        full_response = "".join(response_text)
        parsed = self._parse_json(full_response)

        return [
            Recommendation(url=r.get("url", ""), reason=r.get("reason", ""))
            for r in parsed.get(rec_type, [])
        ]

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from response text."""
        # Try to find <output> tags first
        output_match = re.search(r"<output>\s*(.*?)\s*</output>", text, re.DOTALL)
        if output_match:
            try:
                return json.loads(output_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON block (may be wrapped in markdown code block)
        json_match = re.search(r"```json?\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON object
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: return empty structure
        self.console.print("[yellow]Warning: Could not parse JSON from response[/yellow]")
        return {"convergent": [], "divergent": []}

    def run_sync(
        self,
        context: str,
        n1: int = 5,
        n2: int = 5,
        context_augmentation: str = "",
        style_guidance: str = "",
    ) -> DiscoveryResult:
        """Sync wrapper for discover.

        Args:
            context: User's context
            n1: Number of convergent recommendations
            n2: Number of divergent recommendations
            context_augmentation: Additional context (preferences, history)
            style_guidance: Style guidance for HTML output

        Returns:
            DiscoveryResult
        """
        return asyncio.run(
            self.discover(
                context,
                n1,
                n2,
                context_augmentation=context_augmentation,
                style_guidance=style_guidance,
            )
        )

    def get_more_sync(
        self,
        session_id: str,
        rec_type: str,
        count: int = 5,
    ) -> list[Recommendation]:
        """Sync wrapper for get_more.

        Args:
            session_id: Session ID to resume
            rec_type: Type of recommendations
            count: Number of additional recommendations

        Returns:
            List of new recommendations
        """
        return asyncio.run(self.get_more(session_id, rec_type, count))

    def get_resume_command(self) -> Optional[str]:
        """Get the command to resume the last session.

        Returns:
            Command string to resume session, or None if no session
        """
        if self.last_session_id:
            return f"claude -r {self.last_session_id}"
        return None
