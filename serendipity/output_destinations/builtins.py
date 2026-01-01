"""Built-in output destinations: browser, stdout, file.

These are handled specially by the CLI since they're tightly integrated
with existing functionality (feedback server for browser, etc.).
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from serendipity.output_destinations.base import OutputDestination, SendResult

if TYPE_CHECKING:
    from rich.console import Console
    from serendipity.agent import DiscoveryResult
    from serendipity.config.types import DestinationConfig


class BrowserDestination(OutputDestination):
    """Open recommendations in browser with interactive UI.

    This destination is handled specially by cli.py since it requires
    the feedback server and browser integration.
    """

    async def send(
        self,
        content: str,
        result: "DiscoveryResult",
        console: "Console",
    ) -> SendResult:
        # Browser destination is handled by cli.py directly
        # This method exists for API completeness
        return SendResult(
            success=True,
            message="Browser destination handled by CLI",
        )

    def check_ready(self, console: "Console") -> tuple[bool, str]:
        return True, ""


class StdoutDestination(OutputDestination):
    """Print recommendations to stdout (for piping)."""

    async def send(
        self,
        content: str,
        result: "DiscoveryResult",
        console: "Console",
    ) -> SendResult:
        # Print raw content to stdout for piping
        # Use sys.stdout directly to avoid Rich formatting
        sys.stdout.write(content)
        sys.stdout.write("\n")
        sys.stdout.flush()
        return SendResult(success=True, message="Sent to stdout")

    def check_ready(self, console: "Console") -> tuple[bool, str]:
        return True, ""


class FileDestination(OutputDestination):
    """Save recommendations to file only (no browser)."""

    def __init__(self, name: str, config: "DestinationConfig"):
        super().__init__(name, config)
        self.output_path = config.options.get("path", "")

    async def send(
        self,
        content: str,
        result: "DiscoveryResult",
        console: "Console",
    ) -> SendResult:
        # If result already has an HTML path, that's the file
        if result.html_path and result.html_path.exists():
            return SendResult(
                success=True,
                message=f"Saved to {result.html_path}",
            )

        # Otherwise save content to specified path
        if self.output_path:
            path = Path(self.output_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            return SendResult(success=True, message=f"Saved to {path}")

        return SendResult(
            success=False,
            message="No output path specified",
            errors=["Configure options.path for file destination"],
        )

    def check_ready(self, console: "Console") -> tuple[bool, str]:
        return True, ""


def create_builtin_destination(
    name: str,
    config: "DestinationConfig",
) -> OutputDestination:
    """Create a builtin destination by name.

    Args:
        name: Destination name (browser, stdout, file)
        config: Destination configuration

    Returns:
        Appropriate OutputDestination instance
    """
    if name == "browser":
        return BrowserDestination(name, config)
    elif name == "stdout":
        return StdoutDestination(name, config)
    elif name == "file":
        return FileDestination(name, config)
    else:
        raise ValueError(f"Unknown builtin destination: {name}")
