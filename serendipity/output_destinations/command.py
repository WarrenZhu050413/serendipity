"""Command destination: shell out to external CLI tools.

Pipes formatted content to an external command like gmail, slack-cli, etc.
Supports variable substitution in command template.
"""

import asyncio
import os
import shlex
from datetime import datetime
from typing import TYPE_CHECKING

from serendipity.output_destinations.base import OutputDestination, SendResult

if TYPE_CHECKING:
    from rich.console import Console
    from serendipity.agent import DiscoveryResult
    from serendipity.config.types import DestinationConfig


class CommandDestination(OutputDestination):
    """Shell out to external CLI tool.

    Configuration:
        command: Command template with {placeholders}
        format: Format to use (overrides default)
        options: Dict of placeholder values (to, subject, etc.)

    Supported placeholders:
        {to}: recipient (from options or CLI flag)
        {subject}: email subject (from options or CLI flag)
        {date}: current date (YYYY-MM-DD)
        {count}: number of recommendations
    """

    def __init__(self, name: str, config: "DestinationConfig"):
        super().__init__(name, config)
        self.command_template = config.command or ""
        self.options = config.options or {}

    async def send(
        self,
        content: str,
        result: "DiscoveryResult",
        console: "Console",
    ) -> SendResult:
        if not self.command_template:
            return SendResult(
                success=False,
                message="No command configured",
                errors=["Set command in destination config"],
            )

        # Build placeholder context
        context = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "count": len(result.convergent) + len(result.divergent),
            **self.options,  # Include options like to, subject
        }

        # Expand placeholders in command
        try:
            command = self.command_template.format(**context)
        except KeyError as e:
            return SendResult(
                success=False,
                message=f"Missing placeholder: {e}",
                errors=[f"Add {e} to options or provide via CLI flag"],
            )

        # Execute command with content piped to stdin
        console.print(f"[dim]Running: {command}[/dim]")

        try:
            # Parse command into args
            args = shlex.split(command)

            # Run command with content as stdin
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ},
            )

            stdout, stderr = await process.communicate(input=content.encode())

            if process.returncode != 0:
                return SendResult(
                    success=False,
                    message=f"Command failed with exit code {process.returncode}",
                    errors=[stderr.decode() if stderr else "Unknown error"],
                )

            return SendResult(
                success=True,
                message=stdout.decode().strip() if stdout else f"Sent via {self.name}",
            )

        except FileNotFoundError:
            cmd_name = shlex.split(command)[0] if command else "command"
            return SendResult(
                success=False,
                message=f"Command not found: {cmd_name}",
                errors=[f"Install {cmd_name} or check your PATH"],
            )
        except Exception as e:
            return SendResult(
                success=False,
                message=f"Error running command: {e}",
                errors=[str(e)],
            )

    def check_ready(self, console: "Console") -> tuple[bool, str]:
        if not self.command_template:
            return False, "No command configured"

        # Check if the command exists
        import shutil

        try:
            args = shlex.split(self.command_template)
            cmd_name = args[0] if args else ""

            # Handle placeholders in command name
            if "{" in cmd_name:
                # Can't check command with placeholders, assume it's ok
                return True, ""

            if not shutil.which(cmd_name):
                return False, f"Command not found: {cmd_name}"

            return True, ""
        except Exception as e:
            return False, f"Invalid command: {e}"
