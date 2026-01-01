"""Tests for serendipity.models."""

import json

import pytest

from serendipity.models import HtmlStyle, Recommendation, StatusEvent


class TestRecommendation:
    """Test Recommendation dataclass."""

    def test_basic_creation(self):
        """Test creating a recommendation with required fields only."""
        rec = Recommendation(url="https://example.com", reason="Great content")
        assert rec.url == "https://example.com"
        assert rec.reason == "Great content"
        assert rec.approach == "convergent"  # default
        assert rec.media_type == "article"  # default
        assert rec.title is None
        assert rec.thumbnail_url is None
        assert rec.metadata == {}

    def test_full_creation(self):
        """Test creating a recommendation with all fields."""
        rec = Recommendation(
            url="https://youtube.com/watch?v=123",
            reason="Educational video",
            approach="divergent",
            media_type="youtube",
            title="How to Code",
            thumbnail_url="https://img.youtube.com/vi/123/0.jpg",
            metadata={"channel": "CodingChannel", "duration": "15:32"},
        )
        assert rec.url == "https://youtube.com/watch?v=123"
        assert rec.reason == "Educational video"
        assert rec.approach == "divergent"
        assert rec.media_type == "youtube"
        assert rec.title == "How to Code"
        assert rec.thumbnail_url == "https://img.youtube.com/vi/123/0.jpg"
        assert rec.metadata["channel"] == "CodingChannel"
        assert rec.metadata["duration"] == "15:32"

    def test_to_dict_minimal(self):
        """Test to_dict with minimal fields."""
        rec = Recommendation(url="https://example.com", reason="Test")
        d = rec.to_dict()
        assert d["url"] == "https://example.com"
        assert d["reason"] == "Test"
        assert d["approach"] == "convergent"
        assert d["media_type"] == "article"
        assert "title" not in d
        assert "thumbnail_url" not in d
        assert "metadata" not in d

    def test_to_dict_full(self):
        """Test to_dict with all fields."""
        rec = Recommendation(
            url="https://example.com",
            reason="Test",
            approach="divergent",
            media_type="book",
            title="Test Book",
            thumbnail_url="https://covers.example.com/book.jpg",
            metadata={"author": "Jane Doe", "year": 2024},
        )
        d = rec.to_dict()
        assert d["url"] == "https://example.com"
        assert d["reason"] == "Test"
        assert d["approach"] == "divergent"
        assert d["media_type"] == "book"
        assert d["title"] == "Test Book"
        assert d["thumbnail_url"] == "https://covers.example.com/book.jpg"
        assert d["metadata"]["author"] == "Jane Doe"
        assert d["metadata"]["year"] == 2024

    def test_from_dict_simple(self):
        """Test from_dict with simple format (url, reason only)."""
        data = {"url": "https://example.com", "reason": "Simple rec"}
        rec = Recommendation.from_dict(data)
        assert rec.url == "https://example.com"
        assert rec.reason == "Simple rec"
        assert rec.approach == "convergent"  # default
        assert rec.media_type == "article"  # default

    def test_from_dict_with_approach_override(self):
        """Test from_dict with approach parameter override."""
        data = {"url": "https://example.com", "reason": "Test"}
        rec = Recommendation.from_dict(data, approach="divergent")
        assert rec.approach == "divergent"

    def test_from_dict_extended(self):
        """Test from_dict with extended format."""
        data = {
            "url": "https://youtube.com/watch?v=abc",
            "reason": "Great video",
            "type": "youtube",  # Note: uses 'type' key (from JSON output)
            "title": "Video Title",
            "thumbnail_url": "https://img.youtube.com/vi/abc/0.jpg",
            "metadata": {"channel": "TestChannel", "duration": "10:00"},
        }
        rec = Recommendation.from_dict(data)
        assert rec.url == "https://youtube.com/watch?v=abc"
        assert rec.reason == "Great video"
        assert rec.media_type == "youtube"  # parsed from 'type' key
        assert rec.title == "Video Title"
        assert rec.thumbnail_url == "https://img.youtube.com/vi/abc/0.jpg"
        assert rec.metadata["channel"] == "TestChannel"

    def test_from_dict_media_type_key(self):
        """Test from_dict with media_type key (alternative to type)."""
        data = {
            "url": "https://example.com",
            "reason": "Test",
            "media_type": "podcast",
        }
        rec = Recommendation.from_dict(data)
        assert rec.media_type == "podcast"

    def test_from_dict_empty_metadata(self):
        """Test from_dict when metadata is missing."""
        data = {"url": "https://example.com", "reason": "Test"}
        rec = Recommendation.from_dict(data)
        assert rec.metadata == {}

    def test_roundtrip(self):
        """Test that to_dict -> from_dict preserves data."""
        original = Recommendation(
            url="https://example.com/article",
            reason="Great read",
            approach="convergent",
            media_type="article",
            title="Article Title",
            metadata={"publication": "The Atlantic", "read_time": "5 min"},
        )
        data = original.to_dict()
        restored = Recommendation.from_dict(data)
        assert restored.url == original.url
        assert restored.reason == original.reason
        assert restored.approach == original.approach
        assert restored.media_type == original.media_type
        assert restored.title == original.title
        assert restored.metadata == original.metadata


class TestHtmlStyle:
    """Test HtmlStyle dataclass."""

    def test_creation(self):
        """Test creating an HtmlStyle."""
        style = HtmlStyle(description="Dark theme", css="body { background: #000; }")
        assert style.description == "Dark theme"
        assert style.css == "body { background: #000; }"


class TestStatusEvent:
    """Test StatusEvent dataclass for SSE streaming."""

    def test_basic_creation(self):
        """Test creating a status event with required fields."""
        event = StatusEvent(event="status")
        assert event.event == "status"
        assert event.data == {}

    def test_creation_with_data(self):
        """Test creating a status event with data."""
        event = StatusEvent(event="tool_use", data={"tool": "WebSearch", "query": "test"})
        assert event.event == "tool_use"
        assert event.data["tool"] == "WebSearch"
        assert event.data["query"] == "test"

    def test_to_sse_simple(self):
        """Test to_sse with simple data."""
        event = StatusEvent(event="status", data={"message": "Loading..."})
        sse = event.to_sse()

        assert sse.startswith("event: status\n")
        assert "data: " in sse
        assert sse.endswith("\n\n")

        # Parse the data portion
        lines = sse.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data: ")][0]
        data_json = json.loads(data_line[6:])  # Skip "data: "
        assert data_json["message"] == "Loading..."

    def test_to_sse_tool_use(self):
        """Test to_sse for tool_use event type."""
        event = StatusEvent(
            event="tool_use",
            data={"tool": "WebSearch", "query": "python async", "message": "🔧 WebSearch \"python async\""},
        )
        sse = event.to_sse()

        assert "event: tool_use\n" in sse

        lines = sse.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data: ")][0]
        data_json = json.loads(data_line[6:])
        assert data_json["tool"] == "WebSearch"
        assert data_json["query"] == "python async"
        assert "🔧" in data_json["message"]

    def test_to_sse_complete(self):
        """Test to_sse for complete event with recommendations."""
        recommendations = [
            {"url": "https://example.com", "reason": "Test", "type": "article"},
        ]
        event = StatusEvent(event="complete", data={"recommendations": recommendations})
        sse = event.to_sse()

        assert "event: complete\n" in sse

        lines = sse.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data: ")][0]
        data_json = json.loads(data_line[6:])
        assert "recommendations" in data_json
        assert len(data_json["recommendations"]) == 1
        assert data_json["recommendations"][0]["url"] == "https://example.com"

    def test_to_sse_error(self):
        """Test to_sse for error event."""
        event = StatusEvent(event="error", data={"message": "Something went wrong"})
        sse = event.to_sse()

        assert "event: error\n" in sse

        lines = sse.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data: ")][0]
        data_json = json.loads(data_line[6:])
        assert data_json["message"] == "Something went wrong"

    def test_to_sse_empty_data(self):
        """Test to_sse with empty data dict."""
        event = StatusEvent(event="status")
        sse = event.to_sse()

        assert "event: status\n" in sse
        assert "data: {}\n" in sse

    def test_to_sse_format(self):
        """Test that SSE format is correct per specification."""
        event = StatusEvent(event="test", data={"key": "value"})
        sse = event.to_sse()

        # SSE format: event: <type>\ndata: <json>\n\n
        lines = sse.split("\n")
        assert lines[0] == "event: test"
        assert lines[1].startswith("data: ")
        assert lines[2] == ""  # Empty line after data
        assert lines[3] == ""  # Second empty line (end of event)
