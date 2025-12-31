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
from serendipity.resources import get_base_template, get_discovery_prompt, get_frontend_design

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

OUTPUT_DIR = Path.home() / ".serendipity" / "output"
WHORL_PORT = 8081
WHORL_LOG_PATH = Path.home() / ".whorl" / "server.log"


def check_whorl_setup(console: Console) -> tuple[bool, str]:
    """Check if Whorl is properly set up.

    Args:
        console: Rich console for output

    Returns:
        Tuple of (is_ready, error_message)
    """
    import shutil

    # Check 1: Is Whorl CLI installed?
    if not shutil.which("whorl"):
        return False, (
            "[red]Whorl not installed.[/red]\n\n"
            "To use Whorl integration, install it first:\n"
            "  [cyan]pip install whorled[/cyan]\n"
            "  [cyan]whorl init[/cyan]\n\n"
            "Then add documents to [cyan]~/.whorl/docs/[/cyan]"
        )

    # Check 2: Is Whorl initialized?
    whorl_home = Path.home() / ".whorl"
    if not whorl_home.exists():
        return False, (
            "[red]Whorl not initialized.[/red]\n\n"
            "Run the following to set up Whorl:\n"
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
            "Continuing without Whorl integration..."
        )

    return True, ""


def ensure_whorl_running(console: Console) -> bool:
    """Ensure the Whorl server is running.

    Args:
        console: Rich console for output

    Returns:
        True if Whorl is running, False if failed to start
    """
    # First check if Whorl is properly set up
    is_ready, error_msg = check_whorl_setup(console)
    if not is_ready:
        console.print(error_msg)
        # If it's just empty docs, we can still try to run
        if "no documents" not in error_msg.lower():
            return False

    # Check if Whorl is already running
    try:
        response = httpx.get(f"http://localhost:{WHORL_PORT}/health", timeout=2.0)
        if response.status_code == 200:
            console.print(f"[dim]Whorl server already running on port {WHORL_PORT}[/dim]")
            return True
    except httpx.RequestError:
        pass

    # Try to start Whorl server
    console.print(f"[yellow]Starting Whorl server on port {WHORL_PORT}...[/yellow]")
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

        console.print(f"[red]Failed to start Whorl server. Check {WHORL_LOG_PATH}[/red]")
        return False

    except FileNotFoundError:
        console.print("[red]Whorl command not found. Install with: pip install whorled[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Failed to start Whorl: {e}[/red]")
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
    html_path: Optional[Path] = None


class SerendipityAgent:
    """Claude agent for serendipity discovery."""

    def __init__(
        self,
        console: Optional[Console] = None,
        model: str = "opus",
        verbose: bool = False,
        whorl: bool = False,
        server_port: int = 9876,
        template_path: Optional[Path] = None,
    ):
        """Initialize the Serendipity agent.

        Args:
            console: Rich console for output
            model: Claude model to use (haiku, sonnet, opus)
            verbose: Show detailed progress
            whorl: Enable Whorl integration for personalized context
            server_port: Port for the feedback server
            template_path: Path to HTML template (defaults to package template)
        """
        self.console = console or Console()
        self.model = model
        self.verbose = verbose
        self.whorl = whorl
        self.server_port = server_port
        self.prompt_template = get_discovery_prompt()
        # Use provided template path or fall back to package default
        if template_path:
            self.base_template = template_path.read_text()
        else:
            self.base_template = get_base_template()
        self.frontend_design = get_frontend_design()
        self.output_dir = OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.last_session_id: Optional[str] = None
        self.cost_usd: Optional[float] = None

        # Initialize Whorl if enabled
        if self.whorl:
            if not ensure_whorl_running(self.console):
                self.console.print("[yellow]Continuing without Whorl integration[/yellow]")
                self.whorl = False

    def _get_mcp_servers(self) -> dict:
        """Get MCP server configurations for Whorl.

        Returns:
            Dict of MCP server configs for ClaudeAgentOptions
        """
        servers = {}
        if self.whorl:
            servers["whorl"] = {
                "url": f"http://localhost:{WHORL_PORT}/mcp/",
                "type": "http",
                "headers": {
                    "X-Password": "whorl",  # Default Whorl password
                },
            }
        return servers

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
        # Generate output path for this discovery
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"discovery_{timestamp}.html"

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
            template_content=self.base_template,
            frontend_design=self.frontend_design,
        )

        # Build allowed tools list - no Write needed, we handle HTML assembly
        allowed_tools = ["WebFetch", "WebSearch"]

        # Add Whorl MCP tools if enabled
        if self.whorl:
            allowed_tools.extend([
                "mcp__whorl__text_search_text_search_post",
                "mcp__whorl__agent_search_agent_search_post",
                "mcp__whorl__ingest_ingest_post",
                "mcp__whorl__bash_bash_post",
            ])

        # Build options with MCP servers if Whorl is enabled
        mcp_servers = self._get_mcp_servers()
        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt="You are a discovery engine." + (
                " You have access to the user's personal knowledge base via Whorl MCP tools. "
                "IMPORTANT: Search Whorl FIRST using mcp__whorl__text_search_text_search_post "
                "to understand their preferences, interests, and past writings before making recommendations. "
                "This makes your recommendations much more personalized."
                if self.whorl else ""
            ),
            max_turns=50,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers if mcp_servers else None,
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

        # Parse response with separate extractors for recommendations and CSS
        full_response = "".join(response_text)
        parsed = self._parse_response(full_response)

        # Build HTML from template
        html_content = self.base_template
        html_content = html_content.replace("{css}", parsed.get("css", ""))
        html_content = html_content.replace(
            "{convergent_html}",
            self._render_recommendations(parsed.get("convergent", []))
        )
        html_content = html_content.replace(
            "{divergent_html}",
            self._render_recommendations(parsed.get("divergent", []))
        )
        html_content = html_content.replace("{session_id}", session_id)
        html_content = html_content.replace("{server_port}", str(self.server_port))

        # Write HTML to output
        output_path.write_text(html_content)

        # Extract html_style for result
        html_style = None
        if parsed.get("css"):
            html_style = HtmlStyle(
                description="Custom CSS from Claude",
                css=parsed.get("css", ""),
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
            html_path=output_path,
        )

    async def get_more(
        self,
        session_id: str,
        rec_type: str,
        count: int = 5,
        session_feedback: list[dict] = None,
    ) -> list[Recommendation]:
        """Get more recommendations by resuming a session.

        Args:
            session_id: Session ID to resume
            rec_type: Type of recommendations ("convergent" or "divergent")
            count: Number of additional recommendations
            session_feedback: Feedback from current session [{"url": "...", "feedback": "liked"|"disliked"}]

        Returns:
            List of new recommendations
        """
        type_description = (
            "convergent (matching their taste directly)"
            if rec_type == "convergent"
            else "divergent (expanding their palette)"
        )

        # Build feedback context from current session
        feedback_context = ""
        if session_feedback:
            liked = [f["url"] for f in session_feedback if f.get("feedback") == "liked"]
            disliked = [f["url"] for f in session_feedback if f.get("feedback") == "disliked"]
            if liked:
                feedback_context += "\n\nFrom this session, the user LIKED:\n" + "\n".join(f"- {u}" for u in liked)
            if disliked:
                feedback_context += "\n\nFrom this session, the user DISLIKED:\n" + "\n".join(f"- {u}" for u in disliked)
            if feedback_context:
                feedback_context += "\n\nUse this feedback to refine your next recommendations."

        prompt = f"""Give me {count} more {type_description} recommendations, different from what you've already suggested.{feedback_context}

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

        mcp_servers = self._get_mcp_servers()
        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt="You are a discovery engine.",
            max_turns=50,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers if mcp_servers else None,
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

    def _parse_response(self, text: str) -> dict:
        """Extract recommendations and CSS from response text.

        Parses separate <recommendations> JSON and <css> sections to avoid
        JSON parsing failures from CSS special characters.
        """
        result = {"convergent": [], "divergent": [], "css": ""}

        # Extract recommendations JSON from <recommendations> tags
        rec_match = re.search(r"<recommendations>\s*(.*?)\s*</recommendations>", text, re.DOTALL)
        if rec_match:
            try:
                data = json.loads(rec_match.group(1))
                result["convergent"] = data.get("convergent", [])
                result["divergent"] = data.get("divergent", [])
            except json.JSONDecodeError:
                self.console.print("[yellow]Warning: Could not parse recommendations JSON[/yellow]")
                # Fallback: try to extract URLs at minimum
                pass

        # Extract CSS from <css> tags (no JSON parsing needed)
        css_match = re.search(r"<css>\s*(.*?)\s*</css>", text, re.DOTALL)
        if css_match:
            result["css"] = css_match.group(1)

        # Fallback: try legacy formats if no recommendations found
        if not result["convergent"] and not result["divergent"]:
            # Try <output> tags
            output_match = re.search(r"<output>\s*(.*?)\s*</output>", text, re.DOTALL)
            if output_match:
                try:
                    data = json.loads(output_match.group(1))
                    result["convergent"] = data.get("convergent", [])
                    result["divergent"] = data.get("divergent", [])
                except json.JSONDecodeError:
                    pass

            # Try JSON code block
            if not result["convergent"] and not result["divergent"]:
                json_match = re.search(r"```json?\s*(.*?)\s*```", text, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                        result["convergent"] = data.get("convergent", [])
                        result["divergent"] = data.get("divergent", [])
                    except json.JSONDecodeError:
                        pass

        if not result["convergent"] and not result["divergent"]:
            self.console.print("[yellow]Warning: Could not parse recommendations from response[/yellow]")

        return result

    def _render_recommendations(self, recs: list) -> str:
        """Render recommendations list as HTML.

        Args:
            recs: List of recommendation dicts with url and reason

        Returns:
            HTML string with recommendation cards
        """
        if not recs:
            return ""

        html_parts = []
        for r in recs:
            url = r.get("url", "")
            reason = r.get("reason", "")
            # Escape HTML in reason to prevent XSS
            reason = reason.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_parts.append(f'''            <div class="recommendation" data-url="{url}">
                <a href="{url}" target="_blank" rel="noopener">{url}</a>
                <p class="reason">{reason}</p>
                <div class="actions">
                    <button onclick="feedback(this, 'liked')">👍</button>
                    <button onclick="feedback(this, 'disliked')">👎</button>
                </div>
            </div>''')
        return "\n".join(html_parts)

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from response text (legacy method for get_more)."""
        # Try to find <recommendations> tags first (new format)
        rec_match = re.search(r"<recommendations>\s*(.*?)\s*</recommendations>", text, re.DOTALL)
        if rec_match:
            try:
                return json.loads(rec_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try <output> tags (legacy format, takes priority over code blocks)
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
        session_feedback: list[dict] = None,
    ) -> list[Recommendation]:
        """Sync wrapper for get_more.

        Args:
            session_id: Session ID to resume
            rec_type: Type of recommendations
            count: Number of additional recommendations
            session_feedback: Feedback from current session

        Returns:
            List of new recommendations
        """
        return asyncio.run(self.get_more(session_id, rec_type, count, session_feedback))

    def get_resume_command(self) -> Optional[str]:
        """Get the command to resume the last session.

        Returns:
            Command string to resume session, or None if no session
        """
        if self.last_session_id:
            return f"claude -r {self.last_session_id}"
        return None
