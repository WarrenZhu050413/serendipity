"""Output destinations plugin system.

Provides a unified interface for output destinations:
- builtin: browser, stdout, file (handled internally)
- command: Shell out to external CLI tools
- webhook: HTTP POST to webhook URLs

Usage:
    from serendipity.output_destinations import DestinationManager

    # Create manager from types config
    manager = DestinationManager(types_config.output, console)

    # Get a destination by name
    dest = manager.get_destination("gmail")

    # Format and send
    content = render_markdown(result)
    send_result = await dest.send(content, result, console)
"""

from typing import TYPE_CHECKING, Optional

from .base import OutputDestination, SendResult
from .builtins import (
    BrowserDestination,
    FileDestination,
    StdoutDestination,
    create_builtin_destination,
)
from .command import CommandDestination
from .webhook import WebhookDestination

if TYPE_CHECKING:
    from rich.console import Console
    from serendipity.config.types import OutputConfig


class DestinationManager:
    """Manages all output destinations for a discovery session.

    Creates destination instances from config and provides methods to:
    - Get destinations by name
    - Check destination readiness
    - Resolve default destination
    """

    def __init__(self, config: "OutputConfig", console: "Console"):
        """Initialize manager from output config.

        Args:
            config: OutputConfig containing destinations section
            console: Rich console for output
        """
        self.console = console
        self.config = config
        self.destinations: dict[str, OutputDestination] = {}

        # Create destination instances from config
        for name, dest_config in config.destinations.items():
            dest_type = dest_config.type

            if dest_type == "builtin":
                self.destinations[name] = create_builtin_destination(name, dest_config)
            elif dest_type == "command":
                self.destinations[name] = CommandDestination(name, dest_config)
            elif dest_type == "webhook":
                self.destinations[name] = WebhookDestination(name, dest_config)
            else:
                self.console.print(
                    f"[yellow]Unknown destination type '{dest_type}' for {name}[/yellow]"
                )

    def get_destination(self, name: str) -> Optional[OutputDestination]:
        """Get a destination by name.

        Args:
            name: Destination name (e.g., "gmail", "slack", "browser")

        Returns:
            OutputDestination instance or None if not found
        """
        return self.destinations.get(name)

    def get_default_destination(self) -> Optional[OutputDestination]:
        """Get the default destination from config.

        Returns:
            Default OutputDestination or None
        """
        return self.destinations.get(self.config.default_destination)

    def get_default_format(self) -> str:
        """Get the default format from config.

        Returns:
            Default format name (json, markdown, html)
        """
        return self.config.default_format

    def resolve_format(self, dest_name: str, explicit_format: Optional[str] = None) -> str:
        """Resolve the format to use for a destination.

        Priority:
        1. Explicit format from CLI flag
        2. Destination's format override
        3. Config default format

        Args:
            dest_name: Destination name
            explicit_format: Format explicitly specified (from CLI)

        Returns:
            Format to use
        """
        if explicit_format:
            return explicit_format

        dest = self.get_destination(dest_name)
        if dest and dest.get_format_override():
            return dest.get_format_override()

        return self.config.default_format

    def check_destination_ready(self, name: str) -> tuple[bool, str]:
        """Check if a destination is ready to use.

        Args:
            name: Destination name

        Returns:
            (ready, error_message)
        """
        dest = self.get_destination(name)
        if not dest:
            return False, f"Unknown destination: {name}"

        if not dest.enabled:
            return False, f"Destination {name} is disabled"

        return dest.check_ready(self.console)

    def get_enabled_destination_names(self) -> list[str]:
        """Get names of all enabled destinations.

        Returns:
            List of enabled destination names
        """
        return [
            name for name, dest in self.destinations.items()
            if dest.enabled
        ]

    def list_destinations(self) -> list[tuple[str, str, bool]]:
        """List all destinations with their status.

        Returns:
            List of (name, description, enabled) tuples
        """
        return [
            (name, dest.description, dest.enabled)
            for name, dest in self.destinations.items()
        ]


__all__ = [
    "DestinationManager",
    "OutputDestination",
    "SendResult",
    "BrowserDestination",
    "StdoutDestination",
    "FileDestination",
    "CommandDestination",
    "WebhookDestination",
]
