"""Webhook destination: HTTP POST to webhook URL.

Sends formatted content to a webhook endpoint (Slack, Discord, etc.).
"""

import os
from typing import TYPE_CHECKING

from serendipity.output_destinations.base import OutputDestination, SendResult

if TYPE_CHECKING:
    from rich.console import Console
    from serendipity.agent import DiscoveryResult
    from serendipity.config.types import DestinationConfig


class WebhookDestination(OutputDestination):
    """HTTP POST to webhook URL.

    Configuration:
        webhook_url: URL to POST to (can use ${ENV_VAR} syntax)
        format: Format to use (overrides default)
        options: Additional options (channel, etc.)

    For Slack webhooks, the content is wrapped in a message payload.
    """

    def __init__(self, name: str, config: "DestinationConfig"):
        super().__init__(name, config)
        self.webhook_url = self._expand_env_vars(config.webhook_url or "")
        self.options = config.options or {}

    def _expand_env_vars(self, value: str) -> str:
        """Expand ${VAR} syntax in webhook URL."""
        import re

        def replace(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        return re.sub(r"\$\{(\w+)\}", replace, value)

    async def send(
        self,
        content: str,
        result: "DiscoveryResult",
        console: "Console",
    ) -> SendResult:
        if not self.webhook_url:
            return SendResult(
                success=False,
                message="No webhook URL configured",
                errors=["Set webhook_url in destination config"],
            )

        try:
            import httpx

            # Build payload based on destination type
            # Default to Slack-style payload
            payload = self._build_payload(content)

            console.print(f"[dim]Posting to webhook...[/dim]")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    timeout=30.0,
                )

                if response.status_code >= 400:
                    return SendResult(
                        success=False,
                        message=f"Webhook returned {response.status_code}",
                        errors=[response.text[:500] if response.text else "No response body"],
                    )

                return SendResult(
                    success=True,
                    message=f"Posted to {self.name}",
                )

        except ImportError:
            return SendResult(
                success=False,
                message="httpx not installed",
                errors=["Run: pip install httpx"],
            )
        except Exception as e:
            return SendResult(
                success=False,
                message=f"Webhook error: {e}",
                errors=[str(e)],
            )

    def _build_payload(self, content: str) -> dict:
        """Build webhook payload from content.

        Detects Slack/Discord webhooks and formats appropriately.
        """
        channel = self.options.get("channel", "")

        # Slack webhook format
        if "slack.com" in self.webhook_url or "hooks.slack.com" in self.webhook_url:
            payload = {"text": content}
            if channel:
                payload["channel"] = channel
            return payload

        # Discord webhook format
        if "discord.com" in self.webhook_url or "discordapp.com" in self.webhook_url:
            return {"content": content[:2000]}  # Discord limit

        # Generic webhook - just send content as text
        return {"text": content, "content": content}

    def check_ready(self, console: "Console") -> tuple[bool, str]:
        if not self.webhook_url:
            return False, "No webhook URL configured"

        # Check if URL looks valid
        if not self.webhook_url.startswith(("http://", "https://")):
            return False, f"Invalid webhook URL: {self.webhook_url}"

        # Check if httpx is installed
        try:
            import httpx  # noqa: F401

            return True, ""
        except ImportError:
            return False, "httpx not installed (pip install httpx)"
