"""Lightweight feedback server for serendipity HTML interaction."""

import asyncio
import errno
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from aiohttp import web

logger = logging.getLogger(__name__)

from serendipity.storage import HistoryEntry, StorageManager


class FeedbackServer:
    """Lightweight HTTP server for handling HTML feedback and 'more' requests."""

    def __init__(
        self,
        storage: StorageManager,
        on_more_request: Optional[Callable] = None,
        idle_timeout: int = 600,  # 10 minutes
        html_content: Optional[str] = None,
        static_dir: Optional[Path] = None,
    ):
        """Initialize feedback server.

        Args:
            storage: Storage manager for persisting feedback
            on_more_request: Callback for "more" requests. Called with (session_id, type, count, session_feedback).
            idle_timeout: Seconds of inactivity before auto-shutdown
            html_content: Optional HTML content to serve at / (legacy mode)
            static_dir: Optional directory to serve static files from
        """
        self.storage = storage
        self.on_more_request = on_more_request
        self.idle_timeout = idle_timeout
        self.html_content = html_content
        self.static_dir = static_dir
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._last_activity = datetime.now()
        self._shutdown_task: Optional[asyncio.Task] = None
        self._running = False
        # Session context storage for /context endpoint
        self.session_inputs: dict[str, str] = {}  # session_id -> user_input

    async def start(self, port: int, max_retries: int = 10) -> int:
        """Start the feedback server.

        Args:
            port: Preferred port to listen on
            max_retries: Maximum number of ports to try if preferred port is taken

        Returns:
            The actual port the server is running on (may differ if preferred was taken)

        Raises:
            OSError: If no available port found after max_retries attempts
        """
        self._app = web.Application()
        self._app.router.add_post("/feedback", self._handle_feedback)
        self._app.router.add_post("/more", self._handle_more)
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/context", self._handle_context)
        self._app.router.add_options("/feedback", self._handle_cors)
        self._app.router.add_options("/more", self._handle_cors)
        self._app.router.add_options("/context", self._handle_cors)

        # Serve static files from static_dir if provided, otherwise use legacy html_content
        if self.static_dir:
            self._app.router.add_get("/{filename}", self._handle_static_file)
            self._app.router.add_get("/", self._handle_index)
        else:
            self._app.router.add_get("/", self._handle_index)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        # Try binding to port, incrementing if taken
        actual_port = port
        last_error = None
        for attempt in range(max_retries):
            try:
                self._site = web.TCPSite(self._runner, "localhost", actual_port)
                await self._site.start()
                if actual_port != port:
                    logger.warning(
                        f"Port {port} was in use, using port {actual_port} instead"
                    )
                self._actual_port = actual_port
                break
            except OSError as e:
                # errno 48 is EADDRINUSE on macOS, 98 on Linux
                if e.errno in (errno.EADDRINUSE, 48, 98):
                    last_error = e
                    actual_port = port + attempt + 1
                else:
                    raise
        else:
            # Exhausted all retries
            await self._runner.cleanup()
            raise OSError(
                f"Could not find available port after {max_retries} attempts "
                f"(tried {port}-{port + max_retries - 1}). Last error: {last_error}"
            )

        self._running = True
        self._last_activity = datetime.now()

        # Start idle timeout checker
        self._shutdown_task = asyncio.create_task(self._idle_shutdown_check())

        return actual_port

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

    async def _handle_context(self, request: web.Request) -> web.Response:
        """Return context data for the context panel.

        Returns JSON with:
        - rules: Discovery rules from rules.md
        - history: Recent history entries with feedback
        - history_summary: Summary file content if exists
        - user_input: The user's input for this session
        """
        self._update_activity()
        session_id = request.query.get("session_id", "")

        # Load learnings
        rules = self.storage.load_learnings()

        # Load recent history (last 20 items)
        recent_history = self.storage.load_recent_history(20)
        history_data = [
            {
                "url": e.url,
                "reason": e.reason,
                "type": e.type,
                "feedback": e.feedback,
                "timestamp": e.timestamp,
            }
            for e in recent_history
        ]

        # Load history summary if exists
        summary_path = self.storage.base_dir / "history_summary.txt"
        history_summary = ""
        if summary_path.exists():
            history_summary = summary_path.read_text()

        # Get user input for this session
        user_input = self.session_inputs.get(session_id, "")

        return web.json_response(
            {
                "rules": rules,
                "history": history_data,
                "history_summary": history_summary,
                "user_input": user_input,
            },
            headers=self._cors_headers(),
        )

    def register_session_input(self, session_id: str, user_input: str) -> None:
        """Register user input for a session.

        Args:
            session_id: The session ID
            user_input: The user's discovery input/context
        """
        self.session_inputs[session_id] = user_input

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

    async def _handle_static_file(self, request: web.Request) -> web.Response:
        """Serve static files from static_dir."""
        self._update_activity()

        if not self.static_dir:
            return web.Response(status=404, text="Not found")

        filename = request.match_info.get("filename", "")
        if not filename:
            return web.Response(status=404, text="Not found")

        # Security: prevent path traversal
        if ".." in filename or filename.startswith("/"):
            return web.Response(status=403, text="Forbidden")

        file_path = self.static_dir / filename
        if not file_path.exists() or not file_path.is_file():
            return web.Response(status=404, text="Not found")

        # Determine content type
        content_type = "text/html" if filename.endswith(".html") else "application/octet-stream"

        return web.Response(
            text=file_path.read_text(),
            content_type=content_type,
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
            "count": 5,
            "session_feedback": [  // Optional: feedback from current session
                {"url": "...", "feedback": "liked" | "disliked"}
            ]
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
        session_feedback = data.get("session_feedback", [])  # NEW: live feedback from session

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
            # Call the callback to get more recommendations (now with session_feedback)
            result = await self.on_more_request(session_id, rec_type, count, session_feedback)

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
