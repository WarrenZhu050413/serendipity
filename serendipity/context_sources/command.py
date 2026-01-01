"""Command-based context sources.

CommandSource runs a shell command and uses stdout as content.
This provides an easy way to integrate external data without writing Python code.

Example config:
```yaml
my_notes:
  type: command
  enabled: true
  command: "cat ~/notes.md | head -100"
  prompt_hint: |
    <notes>
    {content}
    </notes>
  timeout: 30  # optional, defaults to 30 seconds
```
"""

import subprocess
from typing import TYPE_CHECKING

from .base import ContextResult, ContextSource

if TYPE_CHECKING:
    from rich.console import Console
    from serendipity.storage import StorageManager


class CommandSource(ContextSource):
    """Context source that runs a shell command.

    Executes a command and uses its stdout as content.
    Useful for quick integrations without writing Python loaders.
    """

    DEFAULT_TIMEOUT = 30  # seconds

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.command = config.get("command", "")
        self.timeout = config.get("timeout", self.DEFAULT_TIMEOUT)

    async def check_ready(self, console: "Console") -> tuple[bool, str]:
        """Check if command is specified.

        Returns:
            (True, "") if command is set, (False, error) otherwise
        """
        if not self.command:
            return False, f"No command specified for source '{self.name}'"
        return True, ""

    async def load(self, storage: "StorageManager") -> ContextResult:
        """Run command and capture stdout.

        Args:
            storage: StorageManager (unused, but required by interface)

        Returns:
            ContextResult with command output
        """
        if not self.command:
            return ContextResult(
                content="",
                prompt_section="",
                warnings=[f"[{self.name}] No command specified"],
            )

        try:
            result = subprocess.run(
                self.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            content = result.stdout
            warnings = []

            # Capture stderr as warning if there's any
            if result.stderr.strip():
                warnings.append(f"[{self.name}] stderr: {result.stderr.strip()[:200]}")

            # Warn if command failed
            if result.returncode != 0:
                warnings.append(
                    f"[{self.name}] Command exited with code {result.returncode}"
                )

            prompt_section = self.format_prompt_section(content)
            return ContextResult(
                content=content,
                prompt_section=prompt_section,
                warnings=warnings,
            )

        except subprocess.TimeoutExpired:
            return ContextResult(
                content="",
                prompt_section="",
                warnings=[f"[{self.name}] Command timed out after {self.timeout}s"],
            )
        except Exception as e:
            return ContextResult(
                content="",
                prompt_section="",
                warnings=[f"[{self.name}] Command failed: {e}"],
            )
