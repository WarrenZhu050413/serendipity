"""Tests for serendipity server module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from serendipity.server import FeedbackServer
from serendipity.storage import HistoryEntry, StorageManager


class TestFeedbackServerSessionInputs:
    """Tests for session_inputs storage."""

    def test_session_inputs_initialized_empty(self):
        """Test that session_inputs dict starts empty."""
        storage = MagicMock(spec=StorageManager)
        server = FeedbackServer(storage=storage)
        assert server.session_inputs == {}

    def test_register_session_input(self):
        """Test registering session input."""
        storage = MagicMock(spec=StorageManager)
        server = FeedbackServer(storage=storage)

        server.register_session_input("session-123", "My discovery context")

        assert server.session_inputs["session-123"] == "My discovery context"

    def test_register_multiple_sessions(self):
        """Test registering input for multiple sessions."""
        storage = MagicMock(spec=StorageManager)
        server = FeedbackServer(storage=storage)

        server.register_session_input("session-1", "Context 1")
        server.register_session_input("session-2", "Context 2")

        assert len(server.session_inputs) == 2
        assert server.session_inputs["session-1"] == "Context 1"
        assert server.session_inputs["session-2"] == "Context 2"

    def test_register_overwrites_existing(self):
        """Test that re-registering overwrites existing input."""
        storage = MagicMock(spec=StorageManager)
        server = FeedbackServer(storage=storage)

        server.register_session_input("session-1", "Original")
        server.register_session_input("session-1", "Updated")

        assert server.session_inputs["session-1"] == "Updated"


class TestFeedbackServerMoreEndpoint:
    """Tests for the /more endpoint accepting session_feedback."""

    @pytest.fixture
    def storage(self):
        """Create mock storage."""
        storage = MagicMock(spec=StorageManager)
        storage.load_all_history.return_value = []
        storage.load_recent_history.return_value = []
        return storage

    @pytest.mark.asyncio
    async def test_more_callback_receives_session_feedback(self, storage):
        """Test that on_more_request callback receives session_feedback."""
        received_args = {}

        async def on_more_request(session_id, rec_type, count, session_feedback):
            received_args["session_id"] = session_id
            received_args["rec_type"] = rec_type
            received_args["count"] = count
            received_args["session_feedback"] = session_feedback
            return []

        server = FeedbackServer(storage=storage, on_more_request=on_more_request)

        # Simulate the request handling
        request = MagicMock()
        request.json = AsyncMock(return_value={
            "session_id": "test-session",
            "type": "convergent",
            "count": 5,
            "session_feedback": [
                {"url": "https://liked.com", "feedback": "liked"},
                {"url": "https://disliked.com", "feedback": "disliked"},
            ]
        })

        response = await server._handle_more(request)

        assert received_args["session_id"] == "test-session"
        assert received_args["rec_type"] == "convergent"
        assert received_args["count"] == 5
        assert len(received_args["session_feedback"]) == 2
        assert received_args["session_feedback"][0]["feedback"] == "liked"

    @pytest.mark.asyncio
    async def test_more_callback_with_empty_session_feedback(self, storage):
        """Test that callback receives empty list when no session_feedback."""
        received_args = {}

        async def on_more_request(session_id, rec_type, count, session_feedback):
            received_args["session_feedback"] = session_feedback
            return []

        server = FeedbackServer(storage=storage, on_more_request=on_more_request)

        request = MagicMock()
        request.json = AsyncMock(return_value={
            "session_id": "test-session",
            "type": "convergent",
            "count": 5,
        })

        await server._handle_more(request)

        assert received_args["session_feedback"] == []


class TestFeedbackServerContextEndpoint:
    """Tests for the /context endpoint."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create a real storage manager with temp directory."""
        storage = StorageManager(base_dir=tmp_path)
        storage.ensure_dirs()
        return storage

    @pytest.mark.asyncio
    async def test_context_returns_rules(self, storage):
        """Test that /context returns learnings content."""
        storage.save_learnings("# My Rules\n\n## Likes\n\n### Deep content\nI like deep dives")

        server = FeedbackServer(storage=storage)

        request = MagicMock()
        request.query = {"session_id": "test"}

        response = await server._handle_context(request)

        data = json.loads(response.text)
        assert "My Rules" in data["rules"]
        assert "Deep content" in data["rules"]

    @pytest.mark.asyncio
    async def test_context_returns_history(self, storage):
        """Test that /context returns recent history."""
        entries = [
            HistoryEntry(
                url="https://example.com",
                reason="Great article",
                type="convergent",
                feedback="liked",
                timestamp="2024-01-01T00:00:00",
                session_id="session-1",
            ),
        ]
        storage.append_history(entries)

        server = FeedbackServer(storage=storage)

        request = MagicMock()
        request.query = {"session_id": "test"}

        response = await server._handle_context(request)

        data = json.loads(response.text)
        assert len(data["history"]) == 1
        assert data["history"][0]["url"] == "https://example.com"
        assert data["history"][0]["feedback"] == "liked"

    @pytest.mark.asyncio
    async def test_context_returns_user_input(self, storage):
        """Test that /context returns user input for session."""
        server = FeedbackServer(storage=storage)
        server.register_session_input("my-session", "Find me interesting AI papers")

        request = MagicMock()
        request.query = {"session_id": "my-session"}

        response = await server._handle_context(request)

        data = json.loads(response.text)
        assert data["user_input"] == "Find me interesting AI papers"

    @pytest.mark.asyncio
    async def test_context_returns_empty_user_input_for_unknown_session(self, storage):
        """Test that unknown session returns empty user_input."""
        server = FeedbackServer(storage=storage)

        request = MagicMock()
        request.query = {"session_id": "unknown-session"}

        response = await server._handle_context(request)

        data = json.loads(response.text)
        assert data["user_input"] == ""

    @pytest.mark.asyncio
    async def test_context_returns_history_summary(self, storage):
        """Test that /context returns history summary if exists."""
        summary_path = storage.base_dir / "history_summary.txt"
        summary_path.write_text("User prefers deep technical content")

        server = FeedbackServer(storage=storage)

        request = MagicMock()
        request.query = {"session_id": "test"}

        response = await server._handle_context(request)

        data = json.loads(response.text)
        assert data["history_summary"] == "User prefers deep technical content"

    @pytest.mark.asyncio
    async def test_context_empty_when_no_data(self, storage):
        """Test that /context returns empty values when no data exists."""
        server = FeedbackServer(storage=storage)

        request = MagicMock()
        request.query = {"session_id": "test"}

        response = await server._handle_context(request)

        data = json.loads(response.text)
        assert data["rules"] == ""
        assert data["history"] == []
        assert data["history_summary"] == ""
        assert data["user_input"] == ""


class TestFeedbackServerCors:
    """Tests for CORS handling."""

    def test_cors_headers_include_context(self):
        """Test that CORS headers are set correctly."""
        storage = MagicMock(spec=StorageManager)
        server = FeedbackServer(storage=storage)

        headers = server._cors_headers()

        assert headers["Access-Control-Allow-Origin"] == "*"
        assert "POST" in headers["Access-Control-Allow-Methods"]
        assert "OPTIONS" in headers["Access-Control-Allow-Methods"]
