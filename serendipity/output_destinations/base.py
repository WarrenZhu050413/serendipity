"""Base classes for output destinations.

Output destinations define where to send formatted recommendations:
- builtin: browser, stdout, file (handled internally)
- command: Shell out to external CLI tool
- webhook: HTTP POST to webhook URL
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from rich.console import Console
    from serendipity.agent import DiscoveryResult
    from serendipity.config.types import DestinationConfig


@dataclass
class SendResult:
    """Result from sending to a destination."""

    success: bool
    message: str = ""
    errors: list[str] = field(default_factory=list)


class OutputDestination(ABC):
    """Base class for all output destinations.

    Output destinations receive formatted content and send it somewhere:
    - BuiltinDestination: browser, stdout, file (handled internally)
    - CommandDestination: Shells out to external CLI tool
    - WebhookDestination: HTTP POST to webhook URL
    """

    def __init__(self, name: str, config: "DestinationConfig"):
        """Initialize output destination.

        Args:
            name: Destination name (e.g., "gmail", "slack")
            config: Destination configuration
        """
        self.name = name
        self.config = config
        self.enabled = config.enabled
        self.description = config.description

    @abstractmethod
    async def send(
        self,
        content: str,
        result: "DiscoveryResult",
        console: "Console",
    ) -> SendResult:
        """Send formatted content to destination.

        Args:
            content: Formatted content (markdown, json, etc.)
            result: Full discovery result for additional context
            console: Console for output/progress

        Returns:
            SendResult with success status and any errors
        """
        pass

    @abstractmethod
    def check_ready(self, console: "Console") -> tuple[bool, str]:
        """Check if destination is ready to use.

        Args:
            console: Console for output

        Returns:
            (ready, error_message) - error_message only used if not ready
        """
        pass

    def get_format_override(self) -> Optional[str]:
        """Return format this destination requires, if any.

        Some destinations (like email) may require specific formats.

        Returns:
            Format name (json, markdown, html) or None to use default
        """
        return self.config.format
