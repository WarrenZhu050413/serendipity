"""Lightweight feedback server for serendipity HTML interaction."""

import asyncio
import json
import signal
import sys
from datetime import datetime
from typing import Any, Callable, Optional

from aiohttp import web

from serendipity.storage import HistoryEntry, StorageManager


class FeedbackServer:
    """Lightweight HTTP server for handling HTML feedback and 'more' requests."""

    def __init__(
        self,
        storage: StorageManager,
        on_more_request: Optional[Callable] = None,
        idle_timeout: int = 600,  # 10 minutes
        html_content: Optional[str] = None,
    ):
        """Initialize feedback server.

        Args:
            storage: Storage manager for persisting feedback
            on_more_request: Callback for "more" requests. Called with (session_id, type, count).
            idle_timeout: Seconds of inactivity before auto-shutdown
            html_content: Optional HTML content to serve at /
        """
        self.storage = storage
        self.on_more_request = on_more_request
        self.idle_timeout = idle_timeout
        self.html_content = html_content
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._last_activity = datetime.now()
        self._shutdown_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self, port: int) -> None:
        """Start the feedback server.

        Args:
            port: Port to listen on
        """
        self._app = web.Application()
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_post("/feedback", self._handle_feedback)
        self._app.router.add_post("/more", self._handle_more)
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_options("/feedback", self._handle_cors)
        self._app.router.add_options("/more", self._handle_cors)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "localhost", port)
        await self._site.start()

        self._running = True
        self._last_activity = datetime.now()

        # Start idle timeout checker
        self._shutdown_task = asyncio.create_task(self._idle_shutdown_check())

    async def stop(self) -> None:
        """Stop the feedback server."""
        self._running = False

        if self._shutdown_task:
            self._shutdown_task.cancel()
            try:
                await self._shutdown_task
            except asyncio.CancelledError:
                pass

        if self._runner:
            await self._runner.cleanup()

    async def _idle_shutdown_check(self) -> None:
        """Check for idle timeout and shutdown if exceeded."""
        while self._running:
            await asyncio.sleep(30)  # Check every 30 seconds

            elapsed = (datetime.now() - self._last_activity).total_seconds()
            if elapsed >= self.idle_timeout:
                await self.stop()
                break

    def _update_activity(self) -> None:
        """Update last activity timestamp."""
        self._last_activity = datetime.now()

    def _cors_headers(self) -> dict:
        """Return CORS headers for cross-origin requests from file:// URLs."""
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }

    async def _handle_cors(self, request: web.Request) -> web.Response:
        """Handle CORS preflight requests."""
        return web.Response(headers=self._cors_headers())

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response(
            {"status": "healthy", "service": "serendipity-feedback"},
            headers=self._cors_headers(),
        )

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Serve the HTML page."""
        self._update_activity()
        if self.html_content:
            return web.Response(
                text=self.html_content,
                content_type="text/html",
            )
        return web.Response(
            text="<html><body><h1>Serendipity</h1><p>No content available.</p></body></html>",
            content_type="text/html",
        )

    async def _handle_feedback(self, request: web.Request) -> web.Response:
        """Handle feedback submission.

        Expected JSON body:
        {
            "url": "https://...",
            "session_id": "abc123",
            "feedback": "liked" | "disliked"
        }
        """
        self._update_activity()

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON"},
                status=400,
                headers=self._cors_headers(),
            )

        url = data.get("url")
        session_id = data.get("session_id")
        feedback = data.get("feedback")

        if not all([url, session_id, feedback]):
            return web.json_response(
                {"error": "Missing required fields: url, session_id, feedback"},
                status=400,
                headers=self._cors_headers(),
            )

        if feedback not in ("liked", "disliked"):
            return web.json_response(
                {"error": "feedback must be 'liked' or 'disliked'"},
                status=400,
                headers=self._cors_headers(),
            )

        # Update feedback in history
        updated = self.storage.update_feedback(url, session_id, feedback)

        return web.json_response(
            {"success": updated, "url": url, "feedback": feedback},
            headers=self._cors_headers(),
        )

    async def _handle_more(self, request: web.Request) -> web.Response:
        """Handle 'more' requests for additional recommendations.

        Expected JSON body:
        {
            "session_id": "abc123",
            "type": "convergent" | "divergent",
            "count": 5
        }
        """
        self._update_activity()

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON"},
                status=400,
                headers=self._cors_headers(),
            )

        session_id = data.get("session_id")
        rec_type = data.get("type")
        count = data.get("count", 5)

        if not all([session_id, rec_type]):
            return web.json_response(
                {"error": "Missing required fields: session_id, type"},
                status=400,
                headers=self._cors_headers(),
            )

        if rec_type not in ("convergent", "divergent"):
            return web.json_response(
                {"error": "type must be 'convergent' or 'divergent'"},
                status=400,
                headers=self._cors_headers(),
            )

        if not self.on_more_request:
            return web.json_response(
                {"error": "More requests not supported"},
                status=501,
                headers=self._cors_headers(),
            )

        try:
            # Call the callback to get more recommendations
            result = await self.on_more_request(session_id, rec_type, count)

            return web.json_response(
                {"success": True, "recommendations": result},
                headers=self._cors_headers(),
            )
        except Exception as e:
            return web.json_response(
                {"error": str(e)},
                status=500,
                headers=self._cors_headers(),
            )


async def run_server_with_timeout(
    storage: StorageManager,
    port: int,
    on_more_request: Optional[Callable] = None,
    idle_timeout: int = 600,
) -> None:
    """Run the feedback server until idle timeout or interrupt.

    Args:
        storage: Storage manager
        port: Port to listen on
        on_more_request: Callback for "more" requests
        idle_timeout: Seconds of inactivity before auto-shutdown
    """
    server = FeedbackServer(
        storage=storage,
        on_more_request=on_more_request,
        idle_timeout=idle_timeout,
    )

    # Handle Ctrl+C
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        stop_event.set()

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGINT, signal_handler)
        loop.add_signal_handler(signal.SIGTERM, signal_handler)

    await server.start(port)

    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        await server.stop()
