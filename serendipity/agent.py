"""Claude Agent for serendipity discovery."""

import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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

from serendipity.config.types import TypesConfig
from serendipity.display import AgentDisplay, DisplayConfig
from serendipity.models import HtmlStyle, Recommendation
from serendipity.prompts.builder import PromptBuilder
from serendipity.resources import (
    get_base_template,
    get_default_style,
    get_discovery_prompt,
    get_frontend_design,
    get_system_prompt,
)

# Type hint import to avoid circular import
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from serendipity.context_sources import ContextSourceManager
    from serendipity.storage import StorageManager

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
        context_manager: Optional["ContextSourceManager"] = None,
        server_port: int = 9876,
        template_path: Optional[Path] = None,
        max_thinking_tokens: Optional[int] = None,
        types_config: Optional[TypesConfig] = None,
        storage: Optional["StorageManager"] = None,
    ):
        """Initialize the Serendipity agent.

        Args:
            console: Rich console for output
            model: Claude model to use (haiku, sonnet, opus)
            verbose: Show detailed progress
            context_manager: ContextSourceManager for MCP servers and tools
            server_port: Port for the feedback server
            template_path: Path to HTML template (defaults to package template)
            max_thinking_tokens: Max tokens for extended thinking (None=disabled)
            types_config: TypesConfig for approach/media type guidance
            storage: StorageManager for user-customizable prompts
        """
        self.console = console or Console()
        self.model = model
        self.verbose = verbose
        self.context_manager = context_manager
        self.server_port = server_port
        self.max_thinking_tokens = max_thinking_tokens
        self.types_config = types_config or TypesConfig.default()
        self.prompt_builder = PromptBuilder(self.types_config)

        # Load prompts and style from user paths (auto-creates from defaults on first run)
        if storage:
            self.prompt_template = storage.get_prompt_path(
                "discovery.txt", get_discovery_prompt()
            ).read_text()
            self.frontend_design = storage.get_prompt_path(
                "frontend_design.txt", get_frontend_design()
            ).read_text()
            self.system_prompt = storage.get_prompt_path(
                "system.txt", get_system_prompt()
            ).read_text()
            self.style_css = storage.get_style_path(get_default_style()).read_text()
        else:
            # Fallback to package defaults (for tests without storage)
            self.prompt_template = get_discovery_prompt()
            self.frontend_design = get_frontend_design()
            self.system_prompt = get_system_prompt()
            self.style_css = get_default_style()

        # Use provided template path or fall back to package default
        if template_path:
            self.base_template = template_path.read_text()
        else:
            self.base_template = get_base_template()

        self.output_dir = OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.last_session_id: Optional[str] = None
        self.cost_usd: Optional[float] = None

    def _get_mcp_servers(self) -> dict:
        """Get MCP server configurations from context manager.

        Returns:
            Dict of MCP server configs for ClaudeAgentOptions
        """
        if self.context_manager:
            return self.context_manager.get_mcp_servers()
        return {}

    def _get_allowed_tools(self) -> list[str]:
        """Get allowed tools including MCP tools from context sources.

        Returns:
            List of allowed tool names
        """
        tools = ["WebFetch", "WebSearch"]
        if self.context_manager:
            tools.extend(self.context_manager.get_allowed_tools())
        return tools

    def _get_system_prompt_hints(self) -> str:
        """Get system prompt hints from context sources.

        Returns:
            Additional text for system prompt
        """
        if self.context_manager:
            return self.context_manager.get_system_prompt_hints()
        return ""

    async def discover(
        self,
        context: str,
        context_augmentation: str = "",
    ) -> DiscoveryResult:
        """Run discovery on user context.

        Args:
            context: User's context (text, links, instructions)
            context_augmentation: Additional context (preferences, history)

        Returns:
            DiscoveryResult with recommendations (count from settings.total_count)
        """
        # Generate output path for this discovery
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"discovery_{timestamp}.html"

        # Build full context
        full_context_parts = []
        if context_augmentation:
            full_context_parts.append(context_augmentation)
        full_context_parts.append(f"<current_context>\n{context}\n</current_context>")

        full_context = "\n\n".join(full_context_parts)

        # Build type guidance from config (approaches, media types, distribution)
        type_guidance = self.prompt_builder.build_type_guidance()
        output_format = self.prompt_builder.build_output_schema()

        # Note: template_content and frontend_design are kept for backwards compatibility
        # with user-customized prompts that may still reference them
        prompt = self.prompt_template.format(
            user_context=full_context,
            type_guidance=type_guidance,
            output_format=output_format,
            template_content=self.base_template,
            frontend_design=self.frontend_design,
        )

        # Build allowed tools list from context sources
        allowed_tools = self._get_allowed_tools()

        # Build options with MCP servers from context manager
        mcp_servers = self._get_mcp_servers()
        system_prompt_hints = self._get_system_prompt_hints()

        # Use user-customizable system prompt
        base_system_prompt = self.system_prompt
        if system_prompt_hints:
            base_system_prompt += " " + system_prompt_hints

        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt=base_system_prompt,
            max_turns=50,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers if mcp_servers else None,
            max_thinking_tokens=self.max_thinking_tokens,
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
                        context_sources=self.context_manager.get_enabled_source_names() if self.context_manager else [],
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

        # Parse response for recommendations (CSS now loaded from file)
        full_response = "".join(response_text)
        parsed = self._parse_response(full_response)

        # Build HTML from template with file-based CSS
        html_content = self.base_template
        html_content = html_content.replace("{css}", self.style_css)

        # Combine all recommendations into a single list for masonry grid
        all_recs = parsed.get("convergent", []) + parsed.get("divergent", [])
        html_content = html_content.replace(
            "{recommendations_html}",
            self._render_recommendations(all_recs)
        )
        html_content = html_content.replace("{session_id}", session_id)
        html_content = html_content.replace("{server_port}", str(self.server_port))

        # Write HTML to output
        output_path.write_text(html_content)

        # CSS is now file-based, not generated
        html_style = HtmlStyle(
            description="User CSS from ~/.serendipity/style.css",
            css=self.style_css,
        )

        return DiscoveryResult(
            convergent=parsed.get("convergent", []),
            divergent=parsed.get("divergent", []),
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

        # Build allowed tools list from context sources
        allowed_tools = self._get_allowed_tools()

        mcp_servers = self._get_mcp_servers()
        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt="You are a discovery engine.",
            max_turns=50,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers if mcp_servers else None,
            resume=session_id,  # Resume the previous session
            max_thinking_tokens=self.max_thinking_tokens,
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
            context_sources=self.context_manager.get_enabled_source_names() if self.context_manager else [],
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
        """Extract recommendations from response text.

        Parses <recommendations> JSON section.

        Returns dict with:
            - convergent: list[Recommendation]
            - divergent: list[Recommendation]
        """
        result = {"convergent": [], "divergent": []}

        def parse_recs(data: dict) -> tuple[list[Recommendation], list[Recommendation]]:
            """Parse raw dicts into Recommendation objects."""
            convergent = [
                Recommendation.from_dict(r, approach="convergent")
                for r in data.get("convergent", [])
            ]
            divergent = [
                Recommendation.from_dict(r, approach="divergent")
                for r in data.get("divergent", [])
            ]
            return convergent, divergent

        # Extract recommendations JSON from <recommendations> tags
        rec_match = re.search(r"<recommendations>\s*(.*?)\s*</recommendations>", text, re.DOTALL)
        if rec_match:
            rec_content = rec_match.group(1)
            # Strip markdown code fences if present
            code_match = re.search(r"```json?\s*(.*?)\s*```", rec_content, re.DOTALL)
            if code_match:
                rec_content = code_match.group(1)
            try:
                data = json.loads(rec_content)
                result["convergent"], result["divergent"] = parse_recs(data)
            except json.JSONDecodeError:
                pass  # Will fall through to legacy formats

        # Fallback: try legacy formats if no recommendations found
        if not result["convergent"] and not result["divergent"]:
            # Try <output> tags
            output_match = re.search(r"<output>\s*(.*?)\s*</output>", text, re.DOTALL)
            if output_match:
                try:
                    data = json.loads(output_match.group(1))
                    result["convergent"], result["divergent"] = parse_recs(data)
                except json.JSONDecodeError:
                    pass

            # Try JSON code block
            if not result["convergent"] and not result["divergent"]:
                json_match = re.search(r"```json?\s*(.*?)\s*```", text, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                        result["convergent"], result["divergent"] = parse_recs(data)
                    except json.JSONDecodeError:
                        pass

        if not result["convergent"] and not result["divergent"]:
            self.console.print("[yellow]Warning: Could not parse recommendations from response[/yellow]")

        return result

    def _render_recommendations(self, recs: list[Recommendation]) -> str:
        """Render recommendations list as HTML with slot-based cards.

        Args:
            recs: List of Recommendation objects

        Returns:
            HTML string with recommendation cards featuring slots for
            thumbnail, title, metadata, and reason.
        """
        if not recs:
            return ""

        def escape_html(text: str) -> str:
            """Escape HTML special characters."""
            return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        # Map approach to display label
        approach_labels = {
            "convergent": "More Like This",
            "divergent": "Surprise",
        }

        html_parts = []
        for rec in recs:
            url = escape_html(rec.url)
            reason = escape_html(rec.reason)
            approach = escape_html(rec.approach)
            media_type = escape_html(rec.media_type)

            # Approach and media labels for tags
            approach_label = approach_labels.get(rec.approach, rec.approach.title())
            media_label = rec.media_type.title() if rec.media_type else "Article"

            # Build optional thumbnail slot
            thumbnail_html = ""
            if rec.thumbnail_url:
                thumbnail_html = f'''
                <div class="card-media">
                    <img src="{escape_html(rec.thumbnail_url)}" loading="lazy" alt="">
                </div>'''

            # Build title/URL display
            if rec.title:
                title_html = f'<a href="{url}" class="card-link" target="_blank" rel="noopener">{escape_html(rec.title)}</a>'
            else:
                title_html = f'<a href="{url}" class="card-link card-url" target="_blank" rel="noopener">{url}</a>'

            # Build metadata slot from type-specific fields
            metadata_html = ""
            if rec.metadata:
                meta_items = []
                for key, value in rec.metadata.items():
                    if value:
                        meta_items.append(f'<span>{escape_html(key)}: {escape_html(str(value))}</span>')
                if meta_items:
                    metadata_html = f'<div class="card-meta">{" ".join(meta_items)}</div>'

            html_parts.append(f'''        <div class="card" data-url="{url}" data-approach="{approach}" data-media="{media_type}">
            <div class="card-tags">
                <span class="tag approach {approach}">{approach_label}</span>
                <span class="tag media {media_type}">{media_label}</span>
            </div>{thumbnail_html}
            <div class="card-content">
                {title_html}
                {metadata_html}
                <p class="card-reason">{reason}</p>
            </div>
            <div class="card-actions">
                <button onclick="feedback(this, 'liked')">👍</button>
                <button onclick="feedback(this, 'disliked')">👎</button>
            </div>
        </div>''')
        return "\n".join(html_parts)

    def render_markdown(self, result: DiscoveryResult) -> str:
        """Render discovery result as markdown for email/chat.

        Args:
            result: DiscoveryResult with recommendations

        Returns:
            Markdown-formatted string with all recommendations
        """
        parts = []

        # Header
        parts.append("# Serendipity Discoveries")
        parts.append("")

        # Convergent recommendations
        if result.convergent:
            parts.append("## More Like This")
            parts.append("")
            for rec in result.convergent:
                parts.append(self._format_recommendation_md(rec))
            parts.append("")

        # Divergent recommendations
        if result.divergent:
            parts.append("## Surprises")
            parts.append("")
            for rec in result.divergent:
                parts.append(self._format_recommendation_md(rec))
            parts.append("")

        return "\n".join(parts)

    def _format_recommendation_md(self, rec: Recommendation) -> str:
        """Format a single recommendation as markdown.

        Args:
            rec: Recommendation to format

        Returns:
            Markdown string for this recommendation
        """
        lines = []

        # Title or URL as heading
        if rec.title:
            lines.append(f"### [{rec.title}]({rec.url})")
        else:
            lines.append(f"### [{rec.url}]({rec.url})")

        # Media type badge
        media_label = rec.media_type.title() if rec.media_type else "Article"
        lines.append(f"*{media_label}*")
        lines.append("")

        # Metadata if present
        if rec.metadata:
            meta_parts = []
            for key, value in rec.metadata.items():
                if value:
                    meta_parts.append(f"**{key}:** {value}")
            if meta_parts:
                lines.append(" | ".join(meta_parts))
                lines.append("")

        # Reason
        lines.append(rec.reason)
        lines.append("")

        return "\n".join(lines)

    def render_json(self, result: DiscoveryResult) -> str:
        """Render discovery result as JSON for piping.

        Args:
            result: DiscoveryResult with recommendations

        Returns:
            JSON string with recommendations
        """
        output = {
            "convergent": [
                {
                    "url": r.url,
                    "title": r.title,
                    "reason": r.reason,
                    "media_type": r.media_type,
                    "metadata": r.metadata,
                }
                for r in result.convergent
            ],
            "divergent": [
                {
                    "url": r.url,
                    "title": r.title,
                    "reason": r.reason,
                    "media_type": r.media_type,
                    "metadata": r.metadata,
                }
                for r in result.divergent
            ],
        }
        return json.dumps(output, indent=2)

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
        context_augmentation: str = "",
    ) -> DiscoveryResult:
        """Sync wrapper for discover.

        Args:
            context: User's context
            context_augmentation: Additional context (preferences, history)

        Returns:
            DiscoveryResult
        """
        return asyncio.run(
            self.discover(
                context,
                context_augmentation=context_augmentation,
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
