"""Lightweight feedback server for serendipity HTML interaction."""

import asyncio
import errno
import json
import logging
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from aiohttp import web

logger = logging.getLogger(__name__)

from serendipity.learnings_parser import (
    Learning,
    add_learning,
    delete_learning_by_id,
    parse_learnings,
    serialize_learnings,
    update_learning_by_id,
)
from serendipity.storage import HistoryEntry, StorageManager, VersionInfo


class FeedbackServer:
    """Lightweight HTTP server for handling HTML feedback and 'more' requests."""

    def __init__(
        self,
        storage: StorageManager,
        on_more_request: Optional[Callable] = None,
        on_more_stream_request: Optional[Callable] = None,
        idle_timeout: int = 600,  # 10 minutes
        html_content: Optional[str] = None,
        static_dir: Optional[Path] = None,
    ):
        """Initialize feedback server.

        Args:
            storage: Storage manager for persisting feedback
            on_more_request: Callback for "more" requests. Called with
                (session_id, type, count, session_feedback, profile_diffs, custom_directives).
                - profile_diffs: Optional dict of {section_name: diff_text} for profile changes
                - custom_directives: Optional string with user's custom instructions for this batch
            on_more_stream_request: Callback for streaming "more" requests. Returns an async
                generator that yields StatusEvent objects for SSE streaming.
            idle_timeout: Seconds of inactivity before auto-shutdown
            html_content: Optional HTML content to serve at / (legacy mode)
            static_dir: Optional directory to serve static files from
        """
        self.storage = storage
        self.on_more_request = on_more_request
        self.on_more_stream_request = on_more_stream_request
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
        self._app.router.add_post("/more/stream", self._handle_more_stream)
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/context", self._handle_context)
        self._app.router.add_options("/feedback", self._handle_cors)
        self._app.router.add_options("/more", self._handle_cors)
        self._app.router.add_options("/more/stream", self._handle_cors)
        self._app.router.add_options("/context", self._handle_cors)

        # API endpoints for profile/settings management
        # Profile: taste
        self._app.router.add_get("/api/profile/taste", self._handle_get_taste)
        self._app.router.add_post("/api/profile/taste", self._handle_save_taste)
        self._app.router.add_options("/api/profile/taste", self._handle_cors)

        # Profile: learnings
        self._app.router.add_get("/api/profile/learnings", self._handle_get_learnings)
        self._app.router.add_post("/api/profile/learnings", self._handle_add_learning)
        self._app.router.add_options("/api/profile/learnings", self._handle_cors)
        self._app.router.add_delete("/api/profile/learnings/{id}", self._handle_delete_learning)
        self._app.router.add_patch("/api/profile/learnings/{id}", self._handle_update_learning)
        self._app.router.add_options("/api/profile/learnings/{id}", self._handle_cors)

        # Profile: history
        self._app.router.add_get("/api/profile/history", self._handle_get_history)
        self._app.router.add_delete("/api/profile/history", self._handle_delete_history_entry)
        self._app.router.add_options("/api/profile/history", self._handle_cors)

        # Settings
        self._app.router.add_get("/api/settings", self._handle_get_settings)
        self._app.router.add_patch("/api/settings", self._handle_update_settings)
        self._app.router.add_post("/api/settings/reset", self._handle_reset_settings)
        self._app.router.add_options("/api/settings", self._handle_cors)
        self._app.router.add_options("/api/settings/reset", self._handle_cors)

        # Sources
        self._app.router.add_get("/api/sources", self._handle_get_sources)
        self._app.router.add_post("/api/sources/{name}/toggle", self._handle_toggle_source)
        self._app.router.add_options("/api/sources", self._handle_cors)
        self._app.router.add_options("/api/sources/{name}/toggle", self._handle_cors)

        # Version history
        self._app.router.add_get("/api/versions/{file}", self._handle_list_versions)
        self._app.router.add_get("/api/versions/{file}/{version_id}", self._handle_get_version)
        self._app.router.add_post("/api/versions/{file}/{version_id}/restore", self._handle_restore_version)
        self._app.router.add_options("/api/versions/{file}", self._handle_cors)
        self._app.router.add_options("/api/versions/{file}/{version_id}", self._handle_cors)
        self._app.router.add_options("/api/versions/{file}/{version_id}/restore", self._handle_cors)

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
            ],
            "profile_diffs": {  // Optional: changes made to profile since last request
                "taste": "diff content here..."
            },
            "custom_directives": "string"  // Optional: user-provided directives for this batch
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
        session_feedback = data.get("session_feedback", [])
        profile_diffs = data.get("profile_diffs")  # Dict of {section: diff_text}
        custom_directives = data.get("custom_directives", "")  # User's custom instructions

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
            result = await self.on_more_request(
                session_id, rec_type, count, session_feedback, profile_diffs, custom_directives
            )

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

    async def _handle_more_stream(self, request: web.Request) -> web.StreamResponse:
        """Handle 'more' requests with SSE streaming for live status updates.

        Expected JSON body: Same as /more endpoint.

        Returns SSE stream with events:
        - status: General status messages
        - tool_use: Tool calls (WebSearch, etc.)
        - complete: Final result with recommendations
        - error: Error occurred
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
        session_feedback = data.get("session_feedback", [])
        profile_diffs = data.get("profile_diffs")
        custom_directives = data.get("custom_directives", "")

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

        if not self.on_more_stream_request:
            return web.json_response(
                {"error": "Streaming more requests not supported"},
                status=501,
                headers=self._cors_headers(),
            )

        # Set up SSE response
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                **self._cors_headers(),
            },
        )
        await response.prepare(request)

        try:
            # Get the async generator from the callback
            async for event in self.on_more_stream_request(
                session_id, rec_type, count, session_feedback, profile_diffs, custom_directives
            ):
                # Send SSE event
                sse_data = event.to_sse()
                await response.write(sse_data.encode("utf-8"))
                # Flush to ensure immediate delivery
                await response.drain()

        except Exception as e:
            # Send error event
            error_event = f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            await response.write(error_event.encode("utf-8"))

        await response.write_eof()
        return response

    # ============================================================
    # Profile API: Taste
    # ============================================================

    async def _handle_get_taste(self, request: web.Request) -> web.Response:
        """Get taste.md content."""
        self._update_activity()
        content = self.storage.load_taste()
        return web.json_response(
            {"content": content},
            headers=self._cors_headers(),
        )

    async def _handle_save_taste(self, request: web.Request) -> web.Response:
        """Save taste.md content with versioning."""
        self._update_activity()

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON"},
                status=400,
                headers=self._cors_headers(),
            )

        content = data.get("content", "")

        # Save with version backup
        version_id = self.storage.save_with_version(self.storage.taste_path, content)

        return web.json_response(
            {"success": True, "version_id": version_id},
            headers=self._cors_headers(),
        )

    # ============================================================
    # Profile API: Learnings
    # ============================================================

    async def _handle_get_learnings(self, request: web.Request) -> web.Response:
        """Get learnings as structured list."""
        self._update_activity()
        markdown = self.storage.load_learnings()
        learnings = parse_learnings(markdown)
        return web.json_response(
            {"learnings": [l.to_dict() for l in learnings]},
            headers=self._cors_headers(),
        )

    async def _handle_add_learning(self, request: web.Request) -> web.Response:
        """Add a new learning."""
        self._update_activity()

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON"},
                status=400,
                headers=self._cors_headers(),
            )

        learning_type = data.get("type", "like")
        title = data.get("title", "")
        content = data.get("content", "")

        if not title:
            return web.json_response(
                {"error": "title is required"},
                status=400,
                headers=self._cors_headers(),
            )

        # Parse, add, and serialize back
        markdown = self.storage.load_learnings()
        learnings = parse_learnings(markdown)
        learnings = add_learning(learnings, learning_type, title, content)

        # Save with version
        new_markdown = serialize_learnings(learnings)
        version_id = self.storage.save_with_version(self.storage.learnings_path, new_markdown)

        return web.json_response(
            {"success": True, "learnings": [l.to_dict() for l in learnings], "version_id": version_id},
            headers=self._cors_headers(),
        )

    async def _handle_delete_learning(self, request: web.Request) -> web.Response:
        """Delete a learning by ID."""
        self._update_activity()

        learning_id = request.match_info.get("id", "")
        if not learning_id:
            return web.json_response(
                {"error": "Learning ID is required"},
                status=400,
                headers=self._cors_headers(),
            )

        markdown = self.storage.load_learnings()
        learnings = parse_learnings(markdown)
        original_count = len(learnings)

        learnings = delete_learning_by_id(learnings, learning_id)

        if len(learnings) == original_count:
            return web.json_response(
                {"error": "Learning not found"},
                status=404,
                headers=self._cors_headers(),
            )

        # Save with version
        new_markdown = serialize_learnings(learnings)
        version_id = self.storage.save_with_version(self.storage.learnings_path, new_markdown)

        return web.json_response(
            {"success": True, "version_id": version_id},
            headers=self._cors_headers(),
        )

    async def _handle_update_learning(self, request: web.Request) -> web.Response:
        """Update a learning by ID."""
        self._update_activity()

        learning_id = request.match_info.get("id", "")
        if not learning_id:
            return web.json_response(
                {"error": "Learning ID is required"},
                status=400,
                headers=self._cors_headers(),
            )

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON"},
                status=400,
                headers=self._cors_headers(),
            )

        title = data.get("title")
        content = data.get("content")

        markdown = self.storage.load_learnings()
        learnings = parse_learnings(markdown)

        # Check if learning exists
        found = any(l.id == learning_id for l in learnings)
        if not found:
            return web.json_response(
                {"error": "Learning not found"},
                status=404,
                headers=self._cors_headers(),
            )

        learnings = update_learning_by_id(learnings, learning_id, title=title, content=content)

        # Save with version
        new_markdown = serialize_learnings(learnings)
        version_id = self.storage.save_with_version(self.storage.learnings_path, new_markdown)

        return web.json_response(
            {"success": True, "learnings": [l.to_dict() for l in learnings], "version_id": version_id},
            headers=self._cors_headers(),
        )

    # ============================================================
    # Profile API: History
    # ============================================================

    async def _handle_get_history(self, request: web.Request) -> web.Response:
        """Get history entries."""
        self._update_activity()

        limit = int(request.query.get("limit", "50"))
        entries = self.storage.load_recent_history(limit)

        return web.json_response(
            {
                "history": [
                    {
                        "url": e.url,
                        "title": e.title,
                        "reason": e.reason,
                        "type": e.type,
                        "media_type": e.media_type,
                        "feedback": e.feedback,
                        "timestamp": e.timestamp,
                        "session_id": e.session_id,
                    }
                    for e in entries
                ]
            },
            headers=self._cors_headers(),
        )

    async def _handle_delete_history_entry(self, request: web.Request) -> web.Response:
        """Delete a history entry by URL."""
        self._update_activity()

        # URL is passed as query parameter (URL-encoded)
        url = request.query.get("url", "")
        if not url:
            return web.json_response(
                {"error": "url query parameter is required"},
                status=400,
                headers=self._cors_headers(),
            )

        # URL-decode the url parameter
        url = urllib.parse.unquote(url)

        deleted = self.storage.delete_history_entry(url)

        if not deleted:
            return web.json_response(
                {"error": "History entry not found"},
                status=404,
                headers=self._cors_headers(),
            )

        return web.json_response(
            {"success": True},
            headers=self._cors_headers(),
        )

    # ============================================================
    # Settings API
    # ============================================================

    async def _handle_get_settings(self, request: web.Request) -> web.Response:
        """Get current settings."""
        self._update_activity()

        if self.storage.settings_path.exists():
            settings = yaml.safe_load(self.storage.settings_path.read_text()) or {}
        else:
            settings = {}

        return web.json_response(
            {"settings": settings},
            headers=self._cors_headers(),
        )

    async def _handle_update_settings(self, request: web.Request) -> web.Response:
        """Update settings (partial merge)."""
        self._update_activity()

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON"},
                status=400,
                headers=self._cors_headers(),
            )

        updates = data.get("settings", data)

        # Save with version backup first
        if self.storage.settings_path.exists():
            self.storage._create_version_backup(self.storage.settings_path)

        self.storage.update_settings_yaml(updates)

        # Return updated settings
        settings = yaml.safe_load(self.storage.settings_path.read_text()) or {}

        return web.json_response(
            {"success": True, "settings": settings},
            headers=self._cors_headers(),
        )

    async def _handle_reset_settings(self, request: web.Request) -> web.Response:
        """Reset settings to defaults."""
        self._update_activity()

        # Backup current settings
        if self.storage.settings_path.exists():
            self.storage._create_version_backup(self.storage.settings_path)
            self.storage.settings_path.unlink()

        # The next load_config() call will copy defaults

        return web.json_response(
            {"success": True},
            headers=self._cors_headers(),
        )

    # ============================================================
    # Sources API
    # ============================================================

    async def _handle_get_sources(self, request: web.Request) -> web.Response:
        """Get list of context sources with status."""
        self._update_activity()

        if self.storage.settings_path.exists():
            settings = yaml.safe_load(self.storage.settings_path.read_text()) or {}
        else:
            settings = {}

        context_sources = settings.get("context_sources", {})

        sources = []
        for name, config in context_sources.items():
            sources.append({
                "name": name,
                "type": config.get("type", "unknown"),
                "enabled": config.get("enabled", False),
                "description": config.get("description", ""),
            })

        return web.json_response(
            {"sources": sources},
            headers=self._cors_headers(),
        )

    async def _handle_toggle_source(self, request: web.Request) -> web.Response:
        """Toggle a source enabled/disabled."""
        self._update_activity()

        name = request.match_info.get("name", "")
        if not name:
            return web.json_response(
                {"error": "Source name is required"},
                status=400,
                headers=self._cors_headers(),
            )

        if self.storage.settings_path.exists():
            settings = yaml.safe_load(self.storage.settings_path.read_text()) or {}
        else:
            settings = {}

        context_sources = settings.get("context_sources", {})
        if name not in context_sources:
            return web.json_response(
                {"error": f"Source '{name}' not found"},
                status=404,
                headers=self._cors_headers(),
            )

        # Toggle
        current = context_sources[name].get("enabled", False)
        new_enabled = not current

        # Update settings
        self.storage.update_settings_yaml({
            "context_sources": {
                name: {"enabled": new_enabled}
            }
        })

        return web.json_response(
            {"success": True, "name": name, "enabled": new_enabled},
            headers=self._cors_headers(),
        )

    # ============================================================
    # Version History API
    # ============================================================

    def _resolve_file_path(self, file_name: str) -> Optional[Path]:
        """Resolve a file name to a path.

        Supported file names:
        - taste: taste.md
        - learnings: learnings.md
        - settings: settings.yaml
        """
        mapping = {
            "taste": self.storage.taste_path,
            "learnings": self.storage.learnings_path,
            "settings": self.storage.settings_path,
        }
        return mapping.get(file_name)

    async def _handle_list_versions(self, request: web.Request) -> web.Response:
        """List versions for a file."""
        self._update_activity()

        file_name = request.match_info.get("file", "")
        file_path = self._resolve_file_path(file_name)

        if not file_path:
            return web.json_response(
                {"error": f"Unknown file: {file_name}. Supported: taste, learnings, settings"},
                status=400,
                headers=self._cors_headers(),
            )

        versions = self.storage.list_versions(file_path)

        return web.json_response(
            {"versions": [v.to_dict() for v in versions]},
            headers=self._cors_headers(),
        )

    async def _handle_get_version(self, request: web.Request) -> web.Response:
        """Get content of a specific version."""
        self._update_activity()

        file_name = request.match_info.get("file", "")
        version_id = request.match_info.get("version_id", "")

        file_path = self._resolve_file_path(file_name)
        if not file_path:
            return web.json_response(
                {"error": f"Unknown file: {file_name}"},
                status=400,
                headers=self._cors_headers(),
            )

        content = self.storage.get_version_content(file_path, version_id)
        if content is None:
            return web.json_response(
                {"error": f"Version not found: {version_id}"},
                status=404,
                headers=self._cors_headers(),
            )

        return web.json_response(
            {"content": content, "version_id": version_id},
            headers=self._cors_headers(),
        )

    async def _handle_restore_version(self, request: web.Request) -> web.Response:
        """Restore a file to a previous version."""
        self._update_activity()

        file_name = request.match_info.get("file", "")
        version_id = request.match_info.get("version_id", "")

        file_path = self._resolve_file_path(file_name)
        if not file_path:
            return web.json_response(
                {"error": f"Unknown file: {file_name}"},
                status=400,
                headers=self._cors_headers(),
            )

        content = self.storage.restore_version(file_path, version_id)
        if content is None:
            return web.json_response(
                {"error": f"Version not found: {version_id}"},
                status=404,
                headers=self._cors_headers(),
            )

        return web.json_response(
            {"success": True, "content": content},
            headers=self._cors_headers(),
        )
