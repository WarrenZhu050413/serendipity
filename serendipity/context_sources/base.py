"""Base classes for context sources.

Context sources provide user context to the discovery agent through either:
- loader: Python function that returns content to inject into prompt
- mcp: MCP server providing tools for Claude to search
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from rich.console import Console
    from serendipity.storage import StorageManager


@dataclass
class ContextResult:
    """Result from loading a context source."""

    content: str  # Raw content loaded
    prompt_section: str  # Formatted with prompt_hint template
    warnings: list[str] = field(default_factory=list)


@dataclass
class MCPConfig:
    """MCP server configuration for agent."""

    name: str
    url: str
    type: str  # "http" or "sse"
    headers: dict[str, str] = field(default_factory=dict)


class ContextSource(ABC):
    """Base class for all context sources.

    Two types of context sources:
    1. LoaderSource: Calls a Python function to get content, injects into prompt
    2. MCPServerSource: Manages an MCP server, provides tools for Claude
    """

    def __init__(self, name: str, config: dict):
        """Initialize context source.

        Args:
            name: Source name (e.g., "taste", "whorl")
            config: Source configuration from types.yaml
        """
        self.name = name
        self.config = config
        self.enabled = config.get("enabled", True)
        self.prompt_hint = config.get("prompt_hint", "{content}")
        self.description = config.get("description", "")

    @abstractmethod
    async def load(self, storage: "StorageManager") -> ContextResult:
        """Load context from this source.

        Args:
            storage: StorageManager for accessing files/config

        Returns:
            ContextResult with content and formatted prompt section
        """
        pass

    @abstractmethod
    async def check_ready(self, console: "Console") -> tuple[bool, str]:
        """Check if source is ready to use.

        Args:
            console: Console for output

        Returns:
            (ready, error_message) - error_message only used if not ready
        """
        pass

    def get_mcp_config(self) -> Optional[MCPConfig]:
        """Return MCP config if this is an MCP source.

        Returns:
            MCPConfig for MCP sources, None for loaders
        """
        return None

    def get_allowed_tools(self) -> list[str]:
        """Return list of allowed tools for this source.

        Returns:
            List of tool names (e.g., ["mcp__whorl__text_search_post"])
        """
        return []

    def get_system_prompt_hint(self) -> str:
        """Return hint to add to system prompt.

        Returns:
            Text to append to system prompt (e.g., instructions for using MCP tools)
        """
        return ""

    def format_prompt_section(self, content: str) -> str:
        """Format content with prompt_hint template.

        Args:
            content: Raw content to format

        Returns:
            Formatted string with {content} replaced
        """
        if not content.strip():
            return ""
        return self.prompt_hint.format(content=content)
