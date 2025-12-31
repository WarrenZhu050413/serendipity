"""Context sources plugin system.

Provides a unified interface for user context sources:
- loader: Python functions that return content to inject into prompts
- mcp: MCP servers providing tools for Claude to search

Usage:
    from serendipity.context_sources import ContextSourceManager

    # Create manager from types config
    manager = ContextSourceManager(types_config, console)

    # Initialize sources (check setup, start MCP servers)
    warnings = await manager.initialize()

    # Build combined context
    context, load_warnings = await manager.build_context(storage)

    # Get MCP config for agent
    mcp_servers = manager.get_mcp_servers()
    allowed_tools = manager.get_allowed_tools()
    system_hints = manager.get_system_prompt_hints()
"""

from typing import TYPE_CHECKING

from .base import ContextResult, ContextSource, MCPConfig
from .loader import LoaderSource
from .mcp import MCPServerSource

if TYPE_CHECKING:
    from rich.console import Console
    from serendipity.config.types import TypesConfig
    from serendipity.storage import StorageManager


class ContextSourceManager:
    """Manages all context sources for a discovery session.

    Creates source instances from config and provides methods to:
    - Initialize sources (check setup, start MCP servers)
    - Build combined context from all enabled loaders
    - Get MCP server configs for agent
    - Get allowed tools and system prompt hints
    """

    def __init__(self, config: "TypesConfig", console: "Console"):
        """Initialize manager from types config.

        Args:
            config: TypesConfig containing context_sources section
            console: Rich console for output
        """
        self.console = console
        self.sources: dict[str, ContextSource] = {}

        # Create source instances from config
        context_sources = getattr(config, "context_sources", {})
        for name, source_config in context_sources.items():
            # Handle both ContextSourceConfig objects and raw dicts
            if hasattr(source_config, "raw_config"):
                raw_config = source_config.raw_config
                raw_config["enabled"] = source_config.enabled
                raw_config["prompt_hint"] = source_config.prompt_hint
                raw_config["description"] = source_config.description
                source_config = raw_config

            source_type = source_config.get("type", "loader")
            if source_type == "loader":
                self.sources[name] = LoaderSource(name, source_config)
            elif source_type == "mcp":
                self.sources[name] = MCPServerSource(name, source_config)
            else:
                self.console.print(
                    f"[yellow]Unknown source type '{source_type}' for {name}[/yellow]"
                )

    async def initialize(
        self,
        enable_sources: list[str] | None = None,
        disable_sources: list[str] | None = None,
    ) -> list[str]:
        """Initialize all enabled sources.

        Args:
            enable_sources: Sources to explicitly enable (overrides config)
            disable_sources: Sources to explicitly disable (overrides config)

        Returns:
            List of warning messages
        """
        warnings = []

        # Apply enable/disable overrides
        if enable_sources:
            for name in enable_sources:
                if name in self.sources:
                    self.sources[name].enabled = True
                else:
                    warnings.append(f"Unknown source: {name}")

        if disable_sources:
            for name in disable_sources:
                if name in self.sources:
                    self.sources[name].enabled = False

        # Initialize each enabled source
        for name, source in self.sources.items():
            if not source.enabled:
                continue

            ready, error = await source.check_ready(self.console)
            if not ready:
                warnings.append(f"[{name}] {error}")
                source.enabled = False
                continue

            # For MCP sources, ensure server is running
            if isinstance(source, MCPServerSource):
                if not await source.ensure_running(self.console):
                    warnings.append(f"[{name}] Failed to start MCP server")
                    source.enabled = False

        return warnings

    async def build_context(self, storage: "StorageManager") -> tuple[str, list[str]]:
        """Build combined context from all enabled sources.

        Args:
            storage: StorageManager for accessing files/config

        Returns:
            (context_string, warnings)
        """
        parts = []
        all_warnings = []

        for name, source in self.sources.items():
            if not source.enabled:
                continue

            result = await source.load(storage)
            if result.prompt_section:
                parts.append(result.prompt_section)
            all_warnings.extend(result.warnings)

        return "\n\n".join(parts), all_warnings

    def get_mcp_servers(self) -> dict[str, dict]:
        """Get MCP server configs for ClaudeAgentOptions.

        Returns:
            Dict of {server_name: config} for mcp_servers parameter
        """
        servers = {}
        for name, source in self.sources.items():
            if not source.enabled:
                continue
            mcp_config = source.get_mcp_config()
            if mcp_config:
                servers[mcp_config.name] = {
                    "url": mcp_config.url,
                    "type": mcp_config.type,
                    "headers": mcp_config.headers,
                }
        return servers

    def get_allowed_tools(self) -> list[str]:
        """Get all allowed tools from enabled sources.

        Returns:
            List of tool names (e.g., ["mcp__whorl__text_search_post"])
        """
        tools = []
        for source in self.sources.values():
            if source.enabled:
                tools.extend(source.get_allowed_tools())
        return tools

    def get_system_prompt_hints(self) -> str:
        """Get combined system prompt hints from all sources.

        Returns:
            Combined hint text to append to system prompt
        """
        hints = []
        for source in self.sources.values():
            if source.enabled:
                hint = source.get_system_prompt_hint()
                if hint:
                    hints.append(hint.strip())
        return " ".join(hints)

    def get_enabled_source_names(self) -> list[str]:
        """Get names of all enabled sources.

        Returns:
            List of enabled source names
        """
        return [name for name, source in self.sources.items() if source.enabled]


__all__ = [
    "ContextSourceManager",
    "ContextSource",
    "ContextResult",
    "MCPConfig",
    "LoaderSource",
    "MCPServerSource",
]
