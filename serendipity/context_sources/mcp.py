"""MCP server context sources.

MCPServerSource manages an MCP server lifecycle and provides tools for Claude.
Unlike LoaderSource, MCP sources don't inject content directly - they provide
tools that Claude can use to search for context.

Example: Whorl provides search tools for a personal knowledge base.
"""

import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import httpx

from .base import ContextResult, ContextSource, MCPConfig

if TYPE_CHECKING:
    from rich.console import Console
    from serendipity.storage import StorageManager


def _is_port_available(port: int) -> bool:
    """Check if a port is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("localhost", port))
            return True
        except OSError:
            return False


class MCPServerSource(ContextSource):
    """Context source that manages an MCP server.

    Config schema:
    ```yaml
    whorl:
      type: mcp
      enabled: false
      description: "Personal knowledge base via Whorl"
      server:
        url: http://localhost:{port}/mcp/
        type: http
        headers:
          X-Password: whorl
      health_check:
        endpoint: /health
        timeout: 2.0
      setup:
        cli_command: whorl
        install_hint: "pip install whorled && whorl init"
        home_dir: ~/.whorl
        docs_dir: ~/.whorl/docs/
      port:
        default: 8081
        max_retries: 10
      auto_start:
        enabled: true
        command: ["whorl", "server", "--port", "{port}"]
        log_path: ~/.whorl/server.log
      tools:
        allowed:
          - mcp__whorl__text_search_text_search_post
          - mcp__whorl__agent_search_agent_search_post
      system_prompt_hint: |
        Search Whorl FIRST to understand preferences before recommending.
    ```
    """

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self._port: Optional[int] = None
        self._process: Optional[subprocess.Popen] = None

    async def check_ready(self, console: "Console") -> tuple[bool, str]:
        """Check if MCP server setup is valid.

        Validates:
        1. CLI command is installed
        2. Home directory exists
        3. Docs directory has content (if specified)

        Returns:
            (True, "") if ready, (False, error_message) if not
        """
        setup = self.config.get("setup", {})

        # Check CLI installed
        cli_cmd = setup.get("cli_command")
        if cli_cmd and not shutil.which(cli_cmd):
            install_hint = setup.get("install_hint", f"pip install {cli_cmd}")
            return False, f"{cli_cmd} not installed. {install_hint}"

        # Check home dir exists
        home_dir = setup.get("home_dir")
        if home_dir:
            home_path = Path(home_dir).expanduser()
            if not home_path.exists():
                cli_cmd = setup.get("cli_command", "the CLI")
                return False, f"{home_dir} not found. Initialize with {cli_cmd}."

        # Check docs directory has content (optional)
        docs_dir = setup.get("docs_dir")
        if docs_dir:
            docs_path = Path(docs_dir).expanduser()
            if not docs_path.exists() or not any(docs_path.iterdir()):
                return False, f"No documents in {docs_dir}"

        return True, ""

    async def ensure_running(self, console: "Console") -> bool:
        """Ensure MCP server is running, starting if needed.

        Args:
            console: Rich console for output

        Returns:
            True if server is running, False if failed
        """
        port_config = self.config.get("port", {})
        default_port = port_config.get("default", 8080)
        max_retries = port_config.get("max_retries", 10)

        health_check = self.config.get("health_check", {})
        health_endpoint = health_check.get("endpoint", "/health")
        health_timeout = health_check.get("timeout", 2.0)

        # Check if already running on any port in range
        for port in range(default_port, default_port + max_retries):
            try:
                url = f"http://localhost:{port}{health_endpoint}"
                response = httpx.get(url, timeout=health_timeout)
                if response.status_code == 200:
                    if port != default_port:
                        console.print(
                            f"[dim]{self.name} server running on port {port} "
                            f"(not default {default_port})[/dim]"
                        )
                    else:
                        console.print(f"[dim]{self.name} server running on port {port}[/dim]")
                    self._port = port
                    return True
            except httpx.RequestError:
                continue

        # Auto-start if configured
        auto_start = self.config.get("auto_start", {})
        if not auto_start.get("enabled", False):
            console.print(f"[yellow]{self.name} server not running (auto_start disabled)[/yellow]")
            return False

        # Find available port
        target_port = None
        for port in range(default_port, default_port + max_retries):
            if _is_port_available(port):
                target_port = port
                break

        if target_port is None:
            console.print(
                f"[red]No available ports in range {default_port}-"
                f"{default_port + max_retries - 1}[/red]"
            )
            return False

        # Build command
        command_template = auto_start.get("command", [])
        command = [c.format(port=target_port) for c in command_template]

        if not command:
            console.print(f"[red]No start command configured for {self.name}[/red]")
            return False

        console.print(f"[yellow]Starting {self.name} server on port {target_port}...[/yellow]")

        try:
            # Setup log file
            log_path_str = auto_start.get("log_path")
            if log_path_str:
                log_path = Path(log_path_str).expanduser()
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_file = open(log_path, "a")
            else:
                log_file = subprocess.DEVNULL

            # Start server
            self._process = subprocess.Popen(
                command,
                stdout=log_file if log_path_str else subprocess.DEVNULL,
                stderr=log_file if log_path_str else subprocess.DEVNULL,
                start_new_session=True,
            )

            # Wait for server to start
            for _ in range(10):
                time.sleep(0.5)
                try:
                    url = f"http://localhost:{target_port}{health_endpoint}"
                    response = httpx.get(url, timeout=health_timeout)
                    if response.status_code == 200:
                        if target_port != default_port:
                            console.print(
                                f"[green]{self.name} server started on port {target_port}[/green] "
                                f"[yellow](port {default_port} was in use)[/yellow]"
                            )
                        else:
                            console.print(
                                f"[green]{self.name} server started on port {target_port}[/green]"
                            )
                        self._port = target_port
                        return True
                except httpx.RequestError:
                    continue

            log_msg = f" Check {log_path_str}" if log_path_str else ""
            console.print(f"[red]Failed to start {self.name} server.{log_msg}[/red]")
            return False

        except FileNotFoundError:
            console.print(f"[red]{command[0]} command not found[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Failed to start {self.name}: {e}[/red]")
            return False

    async def load(self, storage: "StorageManager") -> ContextResult:
        """MCP sources don't load content directly.

        They provide tools for Claude to search, so load returns empty.
        """
        return ContextResult(content="", prompt_section="")

    def get_mcp_config(self) -> Optional[MCPConfig]:
        """Return MCP server configuration.

        Returns:
            MCPConfig if server is running, None otherwise
        """
        if not self._port:
            return None

        server = self.config.get("server", {})
        url_template = server.get("url", f"http://localhost:{{port}}/mcp/")
        url = url_template.format(port=self._port)

        return MCPConfig(
            name=self.name,
            url=url,
            type=server.get("type", "http"),
            headers=server.get("headers", {}),
        )

    def get_allowed_tools(self) -> list[str]:
        """Return list of allowed MCP tools.

        Returns:
            List of tool names from config
        """
        return self.config.get("tools", {}).get("allowed", [])

    def get_system_prompt_hint(self) -> str:
        """Return system prompt hint for using MCP tools.

        Returns:
            Hint text to add to system prompt
        """
        return self.config.get("system_prompt_hint", "")
