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
from serendipity.icons import get_icon_html, get_icon_terminal, get_icons_json
from serendipity.models import HtmlStyle, Pairing, Recommendation, StatusEvent
from serendipity.prompts.builder import PromptBuilder
from serendipity.resources import (
    get_base_template,
    get_default_style,
    get_discovery_prompt,
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
    """Result from a discovery operation.

    Recommendations are keyed by approach name (e.g., 'convergent', 'divergent').
    This allows for dynamic approach types defined in settings.yaml.
    """

    recommendations: dict[str, list[Recommendation]] = field(default_factory=dict)
    pairings: list[Pairing] = field(default_factory=list)
    session_id: str = ""
    cost_usd: Optional[float] = None
    raw_response: Optional[str] = None
    html_style: Optional[HtmlStyle] = None
    html_path: Optional[Path] = None

    # Backwards compatibility properties
    @property
    def convergent(self) -> list[Recommendation]:
        """Get convergent recommendations (backwards compatibility)."""
        return self.recommendations.get("convergent", [])

    @property
    def divergent(self) -> list[Recommendation]:
        """Get divergent recommendations (backwards compatibility)."""
        return self.recommendations.get("divergent", [])

    def all_recommendations(self) -> list[Recommendation]:
        """Get all recommendations across all approaches."""
        all_recs = []
        for recs in self.recommendations.values():
            all_recs.extend(recs)
        return all_recs


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
            self.system_prompt = storage.get_prompt_path(
                "system.txt", get_system_prompt()
            ).read_text()
            self.style_css = storage.get_style_path(get_default_style()).read_text()
        else:
            # Fallback to package defaults (for tests without storage)
            self.prompt_template = get_discovery_prompt()
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

        # Note: template_content kept for backwards compatibility with user-customized prompts
        prompt = self.prompt_template.format(
            user_context=full_context,
            type_guidance=type_guidance,
            output_format=output_format,
            template_content=self.base_template,
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
        html_content = html_content.replace("{icons_json}", get_icons_json())

        # Combine all recommendations into a single list for JSON output
        all_recs = parsed.get("convergent", []) + parsed.get("divergent", [])
        pairings = parsed.get("pairings", [])

        # Convert to JSON for JavaScript rendering (single source of truth)
        import json
        initial_data = {
            "recommendations": [rec.to_dict() for rec in all_recs],
            "pairings": [p.to_dict() for p in pairings]
        }
        html_content = html_content.replace(
            "{initial_data_json}",
            json.dumps(initial_data, indent=2)
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
            recommendations=parsed.get("recommendations", {}),
            pairings=parsed.get("pairings", []),
            session_id=session_id,
            cost_usd=cost_usd,
            raw_response=full_response,
            html_style=html_style,
            html_path=output_path,
        )

    async def discover_stream(
        self,
        context: str,
        context_augmentation: str = "",
    ):
        """Run discovery with SSE streaming status updates.

        Yields StatusEvent objects for real-time progress in the browser.

        Args:
            context: User's context (text, links, instructions)
            context_augmentation: Additional context (preferences, history)

        Yields:
            StatusEvent objects for SSE streaming
        """
        yield StatusEvent(event="status", data={"message": "Starting discovery..."})

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"discovery_{timestamp}.html"

        full_context_parts = []
        if context_augmentation:
            full_context_parts.append(context_augmentation)
            yield StatusEvent(event="status", data={"message": "With profile context"})
        full_context_parts.append(f"<current_context>\n{context}\n</current_context>")
        full_context = "\n\n".join(full_context_parts)

        type_guidance = self.prompt_builder.build_type_guidance()
        output_format = self.prompt_builder.build_output_schema()
        prompt = self.prompt_template.format(
            user_context=full_context,
            type_guidance=type_guidance,
            output_format=output_format,
            template_content=self.base_template,
        )

        allowed_tools = self._get_allowed_tools()
        mcp_servers = self._get_mcp_servers()
        system_prompt_hints = self._get_system_prompt_hints()
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

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)
                async for msg in client.receive_response():
                    if isinstance(msg, SystemMessage) and msg.subtype == "init":
                        logger.info("SDK initialized (streaming)", plugins=[p.get("name") for p in msg.data.get("plugins", [])])
                    elif isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, ToolUseBlock):
                                tool_name = block.name
                                tool_input = block.input or {}
                                if tool_name == "WebSearch":
                                    yield StatusEvent(event="tool_use", data={"tool": tool_name, "query": tool_input.get("query", ""), "message": f'WebSearch "{tool_input.get("query", "")}"'})
                                elif tool_name == "WebFetch":
                                    url = tool_input.get("url", "")
                                    yield StatusEvent(event="tool_use", data={"tool": tool_name, "url": url, "message": f'WebFetch "{url[:60]}..."'})
                                else:
                                    yield StatusEvent(event="tool_use", data={"tool": tool_name, "message": tool_name})
                            elif isinstance(block, TextBlock):
                                response_text.append(block.text)
                    elif isinstance(msg, ResultMessage):
                        session_id = msg.session_id
                        cost_usd = msg.total_cost_usd

            self.last_session_id = session_id
            self.cost_usd = cost_usd
            full_response = "".join(response_text)
            parsed = self._parse_response(full_response)
            all_recs = parsed.get("convergent", []) + parsed.get("divergent", [])
            pairings = parsed.get("pairings", [])

            html_content = self.base_template.replace("{css}", self.style_css)
            html_content = html_content.replace("{icons_json}", get_icons_json())
            html_content = html_content.replace("{initial_data_json}", json.dumps({"recommendations": [r.to_dict() for r in all_recs], "pairings": [p.to_dict() for p in pairings]}, indent=2))
            html_content = html_content.replace("{session_id}", session_id)
            html_content = html_content.replace("{server_port}", str(self.server_port))
            output_path.write_text(html_content)

            yield StatusEvent(event="complete", data={"success": True, "session_id": session_id, "recommendations": [r.to_dict() for r in all_recs], "pairings": [p.to_dict() for p in pairings], "icons": get_icons_json()})
        except Exception as e:
            logger.error("discover_stream error", error=str(e))
            yield StatusEvent(event="error", data={"error": str(e)})

    async def get_more(
        self,
        session_id: str,
        rec_type: str,
        count: int = 5,
        session_feedback: list[dict] = None,
        profile_diffs: dict[str, str] = None,
        custom_directives: str = "",
    ) -> list[Recommendation]:
        """Get more recommendations by resuming a session.

        Args:
            session_id: Session ID to resume
            rec_type: Type of recommendations ("convergent" or "divergent")
            count: Number of additional recommendations
            session_feedback: Feedback from current session [{"url": "...", "feedback": "liked"|"disliked"}]
            profile_diffs: Dict of {section_name: diff_text} for profile changes since last request
            custom_directives: User's custom instructions for this batch

        Returns:
            List of new recommendations
        """
        type_description = (
            "convergent (matching their taste directly)"
            if rec_type == "convergent"
            else "divergent (expanding their palette)"
        )

        # Build feedback context from current session (supports both rating and legacy feedback)
        feedback_context = ""
        if session_feedback:
            # Group by rating intensity (1-5 stars)
            loved = [f["url"] for f in session_feedback if f.get("rating") == 5]
            liked = [f["url"] for f in session_feedback if f.get("rating") == 4]
            neutral = [f["url"] for f in session_feedback if f.get("rating") == 3]
            disliked = [f["url"] for f in session_feedback if f.get("rating") == 2]
            hated = [f["url"] for f in session_feedback if f.get("rating") == 1]

            # Handle legacy feedback format
            for f in session_feedback:
                if "feedback" in f and "rating" not in f:
                    if f["feedback"] == "liked":
                        liked.append(f["url"])
                    elif f["feedback"] == "disliked":
                        disliked.append(f["url"])

            if loved:
                feedback_context += "\n\nFrom this session, the user LOVED (5/5 - strong signal):\n" + "\n".join(f"- {u}" for u in loved)
            if liked:
                feedback_context += "\n\nFrom this session, the user liked (4/5):\n" + "\n".join(f"- {u}" for u in liked)
            if neutral:
                feedback_context += "\n\nFrom this session, the user was neutral about (3/5):\n" + "\n".join(f"- {u}" for u in neutral)
            if disliked:
                feedback_context += "\n\nFrom this session, the user disliked (2/5):\n" + "\n".join(f"- {u}" for u in disliked)
            if hated:
                feedback_context += "\n\nFrom this session, the user strongly disliked (1/5 - avoid similar):\n" + "\n".join(f"- {u}" for u in hated)
            if feedback_context:
                feedback_context += "\n\nUse this feedback to refine your next recommendations. Weight 5/5 items heavily, 1/5 as strong negatives."

        # Build profile update context
        profile_update_context = ""
        if profile_diffs:
            profile_update_context = "\n\n<user_update>\n"
            for section_name, diff_text in profile_diffs.items():
                profile_update_context += f"<{section_name}>\n{diff_text}\n</{section_name}>\n"
            profile_update_context += "</user_update>\n\nThe user has updated their profile. Consider these changes when making recommendations."

        # Build custom directives context
        directives_context = ""
        if custom_directives and custom_directives.strip():
            directives_context = f"\n\n<user_directives>\n{custom_directives.strip()}\n</user_directives>\n\nFollow these custom directives from the user for this batch of recommendations."

        prompt = f"""Give me {count} more {type_description} recommendations, different from what you've already suggested.{feedback_context}{profile_update_context}{directives_context}

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

    async def get_more_stream(
        self,
        session_id: str,
        rec_type: str,
        count: int = 5,
        session_feedback: list[dict] = None,
        profile_diffs: dict[str, str] = None,
        custom_directives: str = "",
    ):
        """Get more recommendations with SSE streaming status updates.

        Yields StatusEvent objects that can be sent via SSE to show
        real-time progress (WebSearch calls, etc.) to the browser.

        Args:
            session_id: Session ID to resume
            rec_type: Type of recommendations ("convergent" or "divergent")
            count: Number of additional recommendations
            session_feedback: Feedback from current session
            profile_diffs: Dict of {section_name: diff_text} for profile changes
            custom_directives: User's custom instructions for this batch

        Yields:
            StatusEvent objects for SSE streaming
        """
        from typing import AsyncGenerator

        # Parse type(s) - can be comma-separated
        types = [t.strip() for t in rec_type.split(",")]
        is_multi_type = len(types) > 1

        # Yield initial status
        display_type = "mixed" if is_multi_type else types[0]
        yield StatusEvent(
            event="status",
            data={"message": f"Getting {count} {display_type} recommendations..."}
        )

        # Build feedback context (supports both rating and legacy feedback)
        feedback_context = ""
        if session_feedback:
            # Group by rating intensity (1-5 stars)
            loved = [f["url"] for f in session_feedback if f.get("rating") == 5]
            liked = [f["url"] for f in session_feedback if f.get("rating") == 4]
            neutral = [f["url"] for f in session_feedback if f.get("rating") == 3]
            disliked = [f["url"] for f in session_feedback if f.get("rating") == 2]
            hated = [f["url"] for f in session_feedback if f.get("rating") == 1]

            # Handle legacy feedback format
            for f in session_feedback:
                if "feedback" in f and "rating" not in f:
                    if f["feedback"] == "liked":
                        liked.append(f["url"])
                    elif f["feedback"] == "disliked":
                        disliked.append(f["url"])

            if loved or liked or neutral or disliked or hated:
                yield StatusEvent(
                    event="status",
                    data={"message": f"With {len(session_feedback)} feedback items"}
                )
            if loved:
                feedback_context += "\n\nFrom this session, the user LOVED (5/5 - strong signal):\n" + "\n".join(f"- {u}" for u in loved)
            if liked:
                feedback_context += "\n\nFrom this session, the user liked (4/5):\n" + "\n".join(f"- {u}" for u in liked)
            if neutral:
                feedback_context += "\n\nFrom this session, the user was neutral about (3/5):\n" + "\n".join(f"- {u}" for u in neutral)
            if disliked:
                feedback_context += "\n\nFrom this session, the user disliked (2/5):\n" + "\n".join(f"- {u}" for u in disliked)
            if hated:
                feedback_context += "\n\nFrom this session, the user strongly disliked (1/5 - avoid similar):\n" + "\n".join(f"- {u}" for u in hated)
            if feedback_context:
                feedback_context += "\n\nUse this feedback to refine your next recommendations. Weight 5/5 items heavily, 1/5 as strong negatives."

        # Build profile update context
        profile_update_context = ""
        if profile_diffs:
            profile_update_context = "\n\n<user_update>\n"
            for section_name, diff_text in profile_diffs.items():
                profile_update_context += f"<{section_name}>\n{diff_text}\n</{section_name}>\n"
            profile_update_context += "</user_update>\n\nThe user has updated their profile. Consider these changes when making recommendations."
            yield StatusEvent(
                event="status",
                data={"message": "With profile updates"}
            )

        # Build custom directives context
        directives_context = ""
        if custom_directives and custom_directives.strip():
            directives_context = f"\n\n<user_directives>\n{custom_directives.strip()}\n</user_directives>\n\nFollow these custom directives from the user for this batch of recommendations."
            # Truncate for display
            display_text = custom_directives[:50] + ("..." if len(custom_directives) > 50 else "")
            yield StatusEvent(
                event="status",
                data={"message": f'Directives: "{display_text}"'}
            )

        # Build JSON output format based on requested types
        if is_multi_type:
            json_format = """{
  "batch_title": "A short evocative title for this batch",
  "convergent": [{"url": "...", "title": "Name of the content", "reason": "...", "type": "article|book|youtube|..."}],
  "divergent": [{"url": "...", "title": "Name of the content", "reason": "...", "type": "article|book|youtube|..."}],
  "pairings": [{"type": "quote|music|tip", "content": "...", "title": "optional link title", "url": "optional url"}]
}"""
        else:
            json_format = f"""{{
  "batch_title": "A short evocative title for this batch",
  "{types[0]}": [{{"url": "...", "title": "Name of the content", "reason": "...", "type": "article|book|youtube|..."}}],
  "pairings": [{{"type": "quote|music|tip", "content": "...", "title": "optional link title", "url": "optional url"}}]
}}"""

        # Simple prompt - model already has approach context from initial discovery
        types_str = " and ".join(types)
        prompt = f"""Give me {count} more {types_str} recommendations, different from what you've already suggested.{feedback_context}{profile_update_context}{directives_context}

Also:
1. Create a thematic title for this batch (something evocative that captures the theme/mood)
2. Suggest 2-3 contextual pairings (quote, music, or tip) that complement these recommendations

Output as JSON:
{json_format}"""

        # Build allowed tools list from context sources
        allowed_tools = self._get_allowed_tools()

        mcp_servers = self._get_mcp_servers()
        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt="You are a discovery engine.",
            max_turns=50,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers if mcp_servers else None,
            resume=session_id,
            max_thinking_tokens=self.max_thinking_tokens,
        )

        response_text = []
        new_session_id = ""
        cost_usd = None

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)

                async for msg in client.receive_response():
                    if isinstance(msg, SystemMessage) and msg.subtype == "init":
                        data = msg.data
                        logger.info(
                            "SDK resumed (streaming)",
                            plugins=[p.get("name") for p in data.get("plugins", [])],
                            mcp_servers=data.get("mcp_servers", []),
                        )

                    elif isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, ThinkingBlock):
                                # Don't stream thinking to reduce noise
                                pass

                            elif isinstance(block, ToolUseBlock):
                                # Stream tool use events
                                tool_name = block.name
                                tool_input = block.input or {}

                                # Format tool use for display
                                if tool_name == "WebSearch":
                                    query = tool_input.get("query", "")
                                    yield StatusEvent(
                                        event="tool_use",
                                        data={
                                            "tool": tool_name,
                                            "query": query,
                                            "message": f'🔧 WebSearch "{query}"'
                                        }
                                    )
                                elif tool_name == "WebFetch":
                                    url = tool_input.get("url", "")
                                    yield StatusEvent(
                                        event="tool_use",
                                        data={
                                            "tool": tool_name,
                                            "url": url,
                                            "message": f'🔧 WebFetch "{url[:60]}..."'
                                        }
                                    )
                                else:
                                    yield StatusEvent(
                                        event="tool_use",
                                        data={
                                            "tool": tool_name,
                                            "message": f"🔧 {tool_name}"
                                        }
                                    )

                            elif isinstance(block, ToolResultBlock):
                                # Just note that result was received, don't stream content
                                pass

                            elif isinstance(block, TextBlock):
                                response_text.append(block.text)

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

            # Collect recommendations from all requested types
            all_recommendations = []
            for t in types:
                for r in parsed.get(t, []):
                    all_recommendations.append({
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "reason": r.get("reason", ""),
                        "approach": t,
                        "media_type": r.get("type", "article"),
                    })

            # Extract batch_title and pairings
            batch_title = parsed.get("batch_title", "")
            pairings = parsed.get("pairings", [])

            # Yield completion event with recommendations, batch_title, and pairings
            yield StatusEvent(
                event="complete",
                data={
                    "success": True,
                    "batch_title": batch_title,
                    "recommendations": all_recommendations,
                    "pairings": pairings
                }
            )

        except Exception as e:
            logger.error("get_more_stream error", error=str(e))
            yield StatusEvent(
                event="error",
                data={"error": str(e)}
            )

    def _parse_response(self, text: str) -> dict:
        """Extract recommendations and pairings from response text.

        Parses <recommendations> JSON section with dynamic approach support.

        Returns dict with:
            - recommendations: dict[str, list[Recommendation]] keyed by approach
            - pairings: list[Pairing]
        """
        result = {"recommendations": {}, "pairings": []}

        # Get enabled approach names from config
        enabled_approaches = {a.name for a in self.types_config.get_enabled_approaches()}
        # Always include convergent/divergent as fallback
        enabled_approaches.update({"convergent", "divergent"})

        def parse_all(data: dict) -> tuple[dict[str, list[Recommendation]], list[Pairing]]:
            """Parse raw dicts into Recommendation and Pairing objects."""
            recommendations: dict[str, list[Recommendation]] = {}

            # Parse each approach dynamically
            for approach_name in enabled_approaches:
                if approach_name in data:
                    recommendations[approach_name] = [
                        Recommendation.from_dict(r, approach=approach_name)
                        for r in data.get(approach_name, [])
                    ]

            # Fallback: handle "recommendations" key (treat as first enabled approach)
            if not recommendations and "recommendations" in data:
                all_recs = data.get("recommendations", [])
                # Use first enabled approach or default to "convergent"
                default_approach = next(iter(enabled_approaches), "convergent")
                recommendations[default_approach] = [
                    Recommendation.from_dict(r, approach=default_approach)
                    for r in all_recs
                ]

            pairings = [
                Pairing.from_dict(p)
                for p in data.get("pairings", [])
            ]
            return recommendations, pairings

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
                result["recommendations"], result["pairings"] = parse_all(data)
            except json.JSONDecodeError:
                pass  # Will fall through to legacy formats

        # Fallback: try legacy formats if no recommendations found
        if not result["recommendations"]:
            # Try <output> tags
            output_match = re.search(r"<output>\s*(.*?)\s*</output>", text, re.DOTALL)
            if output_match:
                try:
                    data = json.loads(output_match.group(1))
                    result["recommendations"], result["pairings"] = parse_all(data)
                except json.JSONDecodeError:
                    pass

            # Try JSON code block
            if not result["recommendations"]:
                json_match = re.search(r"```json?\s*(.*?)\s*```", text, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                        result["recommendations"], result["pairings"] = parse_all(data)
                    except json.JSONDecodeError:
                        pass

        if not result["recommendations"]:
            self.console.print("[yellow]Warning: Could not parse recommendations from response[/yellow]")

        return result

    def _render_recommendations(self, recs: list[Recommendation]) -> str:
        """Render recommendations list as HTML with discovery cards.

        Args:
            recs: List of Recommendation objects

        Returns:
            HTML string with recommendation cards featuring top-right
            feedback buttons, tags, title, metadata, and description.
        """
        if not recs:
            return ""

        def escape_html(text: str) -> str:
            """Escape HTML special characters."""
            return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        # Build approach labels from config dynamically
        approach_labels = {
            name: approach.display_name
            for name, approach in self.types_config.approaches.items()
        }

        # Star SVG for 5-star rating system
        star_svg = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" /></svg>'

        html_parts = []
        for idx, rec in enumerate(recs):
            url = escape_html(rec.url)
            reason = escape_html(rec.reason)
            approach = escape_html(rec.approach)
            media_type = escape_html(rec.media_type)

            # Approach and media labels for tags
            approach_label = approach_labels.get(rec.approach, rec.approach.title())
            media_label = rec.media_type.title() if rec.media_type else "Article"

            # Card accent class (cycles through 6 colors)
            card_class = f"card-{(idx % 6) + 1}"

            # Build title/URL display - title is prominent, URL is smaller
            # Extract domain from URL for cleaner display
            try:
                from urllib.parse import urlparse
                domain = urlparse(rec.url).netloc.replace('www.', '')
            except:
                domain = rec.url[:50]

            if rec.title:
                title_html = f'<a href="{url}" target="_blank" rel="noopener" class="card-title-link">{escape_html(rec.title)}</a>'
                url_html = f'<a href="{url}" target="_blank" rel="noopener" class="card-url">{escape_html(domain)}</a>'
            else:
                # Fallback: use URL as title
                title_html = f'<a href="{url}" target="_blank" rel="noopener" class="card-title-link">{escape_html(domain)}</a>'
                url_html = ""

            # Build metadata slot from type-specific fields
            metadata_html = ""
            if rec.metadata:
                meta_items = []
                for key, value in rec.metadata.items():
                    if value:
                        meta_items.append(f'<span>{escape_html(str(value))}</span>')
                if meta_items:
                    metadata_html = f'<div class="card-meta">{"".join(meta_items)}</div>'

            html_parts.append(f'''                <article class="discovery-card {card_class}" data-url="{url}" data-approach="{approach}" data-media="{media_type}">
                    <div class="card-feedback star-rating" data-rating="0">
                        <span class="star" data-value="1" title="1 star" onmouseover="previewRating(this, 1)" onmouseout="clearPreview(this)" onclick="setRating(this, 1)">{star_svg}</span>
                        <span class="star" data-value="2" title="2 stars" onmouseover="previewRating(this, 2)" onmouseout="clearPreview(this)" onclick="setRating(this, 2)">{star_svg}</span>
                        <span class="star" data-value="3" title="3 stars" onmouseover="previewRating(this, 3)" onmouseout="clearPreview(this)" onclick="setRating(this, 3)">{star_svg}</span>
                        <span class="star" data-value="4" title="4 stars" onmouseover="previewRating(this, 4)" onmouseout="clearPreview(this)" onclick="setRating(this, 4)">{star_svg}</span>
                        <span class="star" data-value="5" title="5 stars" onmouseover="previewRating(this, 5)" onmouseout="clearPreview(this)" onclick="setRating(this, 5)">{star_svg}</span>
                    </div>
                    <div class="card-body">
                        <div class="card-tags">
                            <span class="card-tag approach">{approach_label}</span>
                            <span class="card-tag media">{media_label}</span>
                        </div>
                        <h3 class="card-title">{title_html}</h3>
                        {url_html}
                        {metadata_html}
                        <p class="card-description">{reason}</p>
                    </div>
                </article>''')
        return "\n".join(html_parts)

    def _render_pairings(self, pairings: list[Pairing]) -> str:
        """Render pairings list as HTML for footer section.

        Args:
            pairings: List of Pairing objects

        Returns:
            HTML string with pairing cards
        """
        if not pairings:
            return ""

        def escape_html(text: str) -> str:
            """Escape HTML special characters."""
            return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        # Build icon lookup from config
        pairing_icons = {}
        for p in self.types_config.pairings.values():
            if p.icon:
                pairing_icons[p.name] = p.icon

        html_parts = []
        html_parts.append('<section class="pairings-section">')
        html_parts.append('<h2 class="pairings-title">Pairings</h2>')
        html_parts.append('<div class="pairings-grid">')

        for pairing in pairings:
            icon_name = pairing_icons.get(pairing.type, "")
            # get_icon_html handles fallback automatically
            icon_html = get_icon_html(icon_name) if icon_name else '<span class="pairing-icon-svg">&#10024;</span>'
            type_label = pairing.type.title()
            content = escape_html(pairing.content)

            # Build link if URL present
            if pairing.url:
                title = escape_html(pairing.title or pairing.url)
                link_html = f'<a href="{escape_html(pairing.url)}" target="_blank" rel="noopener" class="pairing-link">{title}</a>'
            else:
                link_html = ""

            html_parts.append(f'''
                <article class="pairing-card pairing-{pairing.type}">
                    <div class="pairing-icon">{icon_html}</div>
                    <div class="pairing-body">
                        <span class="pairing-type">{type_label}</span>
                        <p class="pairing-content">{content}</p>
                        {link_html}
                    </div>
                </article>
            ''')

        html_parts.append('</div>')
        html_parts.append('</section>')

        return "\n".join(html_parts)

    def _render_initial_batch(
        self,
        recs: list[Recommendation],
        pairings: list[Pairing],
        batch_title: str = ""
    ) -> str:
        """Render initial batch as a batch container (title + pairings + cards).

        Args:
            recs: List of Recommendation objects
            pairings: List of Pairing objects
            batch_title: Optional title for this batch

        Returns:
            HTML string with batch container structure
        """
        def escape_html(text: str) -> str:
            """Escape HTML special characters."""
            return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        html_parts = []
        html_parts.append('<div class="batch-container">')

        # 1. Batch header with title (if provided)
        if batch_title:
            html_parts.append(f'''
                <div class="batch-header">
                    <span class="batch-title">{escape_html(batch_title)}</span>
                </div>
            ''')

        # 2. Pairings row
        if pairings:
            # Build icon lookup from config
            pairing_icons = {}
            for p in self.types_config.pairings.values():
                if p.icon:
                    pairing_icons[p.name] = p.icon

            html_parts.append('<div class="batch-pairings">')
            for pairing in pairings:
                icon_name = pairing_icons.get(pairing.type, "")
                icon_html = get_icon_html(icon_name) if icon_name else '<span class="pairing-icon-svg">&#10024;</span>'
                type_label = pairing.type.title()
                content = escape_html(pairing.content)

                # Build link if URL present
                if pairing.url:
                    title = escape_html(pairing.title or pairing.url)
                    link_html = f'<a href="{escape_html(pairing.url)}" target="_blank" rel="noopener" class="pairing-link">{title}</a>'
                else:
                    link_html = ""

                html_parts.append(f'''
                    <article class="pairing-card pairing-{pairing.type}">
                        <div class="pairing-icon">{icon_html}</div>
                        <div class="pairing-body">
                            <span class="pairing-type">{type_label}</span>
                            <p class="pairing-content">{content}</p>
                            {link_html}
                        </div>
                    </article>
                ''')
            html_parts.append('</div>')

        # 3. Cards grid
        if recs:
            html_parts.append('<div class="batch-cards">')
            html_parts.append(self._render_recommendations(recs))
            html_parts.append('</div>')

        html_parts.append('</div>')  # Close batch-container

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

        # Render all approach sections dynamically
        for approach_name, recs in result.recommendations.items():
            if recs:
                # Get display name from config, fallback to title case
                approach_config = self.types_config.approaches.get(approach_name)
                display_name = approach_config.display_name if approach_config else approach_name.title()
                parts.append(f"## {display_name}")
                parts.append("")
                for rec in recs:
                    parts.append(self._format_recommendation_md(rec))
                parts.append("")

        # Pairings section
        if result.pairings:
            parts.append("## Pairings")
            parts.append("")
            # Build icon lookup from config
            pairing_icons = {}
            for p in self.types_config.pairings.values():
                if p.icon:
                    pairing_icons[p.name] = p.icon

            for pairing in result.pairings:
                icon_name = pairing_icons.get(pairing.type, "")
                # get_icon_terminal handles fallback automatically
                icon = get_icon_terminal(icon_name) if icon_name else "✨"
                parts.append(f"### {icon} {pairing.type.title()}")
                parts.append("")
                parts.append(pairing.content)
                if pairing.url:
                    title = pairing.title or pairing.url
                    parts.append(f"[{title}]({pairing.url})")
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
            JSON string with recommendations keyed by approach
        """
        output: dict = {}

        # Add recommendations keyed by approach
        for approach_name, recs in result.recommendations.items():
            output[approach_name] = [
                {
                    "url": r.url,
                    "title": r.title,
                    "reason": r.reason,
                    "media_type": r.media_type,
                    "approach": r.approach,
                    "metadata": r.metadata,
                }
                for r in recs
            ]

        # Add pairings
        output["pairings"] = [
            {
                "type": p.type,
                "content": p.content,
                "url": p.url,
                "title": p.title,
                "metadata": p.metadata,
            }
            for p in result.pairings
        ]

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
