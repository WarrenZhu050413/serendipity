"""Tests for serendipity storage module."""

import json
import tempfile
from pathlib import Path

import pytest

from serendipity.storage import Config, HistoryEntry, StorageManager


class TestHistoryEntry:
    """Tests for HistoryEntry dataclass."""

    def test_create_entry(self):
        """Test creating a basic history entry."""
        entry = HistoryEntry(
            url="https://example.com",
            reason="Great content",
            type="convergent",
            feedback="liked",
            timestamp="2024-01-15T10:30:00Z",
            session_id="abc123",
        )
        assert entry.url == "https://example.com"
        assert entry.feedback == "liked"
        assert entry.extracted is False  # Default value

    def test_extracted_field_default(self):
        """Test that extracted defaults to False."""
        entry = HistoryEntry(
            url="https://example.com",
            reason="test",
            type="convergent",
            feedback=None,
            timestamp="2024-01-15T10:30:00Z",
            session_id="abc123",
        )
        assert entry.extracted is False

    def test_extracted_field_explicit(self):
        """Test setting extracted explicitly."""
        entry = HistoryEntry(
            url="https://example.com",
            reason="test",
            type="convergent",
            feedback="liked",
            timestamp="2024-01-15T10:30:00Z",
            session_id="abc123",
            extracted=True,
        )
        assert entry.extracted is True

    def test_to_dict(self):
        """Test serializing to dictionary."""
        entry = HistoryEntry(
            url="https://example.com",
            reason="Great content",
            type="convergent",
            feedback="liked",
            timestamp="2024-01-15T10:30:00Z",
            session_id="abc123",
            extracted=True,
        )
        d = entry.to_dict()
        assert d["url"] == "https://example.com"
        assert d["extracted"] is True
        assert "extracted" in d

    def test_from_dict(self):
        """Test deserializing from dictionary."""
        d = {
            "url": "https://example.com",
            "reason": "Great content",
            "type": "convergent",
            "feedback": "liked",
            "timestamp": "2024-01-15T10:30:00Z",
            "session_id": "abc123",
            "extracted": True,
        }
        entry = HistoryEntry.from_dict(d)
        assert entry.url == "https://example.com"
        assert entry.extracted is True

    def test_from_dict_missing_extracted(self):
        """Test deserializing from dict without extracted field (backwards compat)."""
        d = {
            "url": "https://example.com",
            "reason": "Great content",
            "type": "convergent",
            "feedback": "liked",
            "timestamp": "2024-01-15T10:30:00Z",
            "session_id": "abc123",
        }
        entry = HistoryEntry.from_dict(d)
        assert entry.extracted is False  # Default


class TestStorageManager:
    """Tests for StorageManager class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def storage(self, temp_dir):
        """Create a StorageManager with temp directory."""
        return StorageManager(base_dir=temp_dir)

    def test_rules_path(self, storage, temp_dir):
        """Test rules_path property."""
        assert storage.rules_path == temp_dir / "rules.md"

    def test_load_rules_empty(self, storage):
        """Test loading rules when file doesn't exist."""
        rules = storage.load_rules()
        assert rules == ""

    def test_save_and_load_rules(self, storage):
        """Test saving and loading rules."""
        content = "# My Rules\n\n## Likes\n\n### Test Rule\nContent here."
        storage.save_rules(content)
        loaded = storage.load_rules()
        assert loaded == content

    def test_append_rule_to_empty(self, storage):
        """Test appending a rule when no rules exist."""
        storage.append_rule("Japanese Minimalism", "I like clean designs.", "like")
        rules = storage.load_rules()
        assert "# My Discovery Rules" in rules
        assert "## Likes" in rules
        assert "### Japanese Minimalism" in rules
        assert "I like clean designs." in rules

    def test_append_rule_to_existing(self, storage):
        """Test appending a rule to existing rules."""
        storage.append_rule("First Rule", "Content 1", "like")
        storage.append_rule("Second Rule", "Content 2", "like")
        rules = storage.load_rules()
        assert "### First Rule" in rules
        assert "### Second Rule" in rules

    def test_append_dislike_rule(self, storage):
        """Test appending a dislike rule."""
        storage.append_rule("Clickbait", "I don't like clickbait.", "dislike")
        rules = storage.load_rules()
        assert "## Dislikes" in rules
        assert "### Clickbait" in rules

    def test_clear_rules(self, storage):
        """Test clearing rules."""
        storage.append_rule("Test", "Content", "like")
        assert storage.load_rules() != ""
        storage.clear_rules()
        assert storage.load_rules() == ""

    def test_mark_extracted(self, storage):
        """Test marking entries as extracted."""
        entries = [
            HistoryEntry(
                url="https://example1.com",
                reason="test1",
                type="convergent",
                feedback="liked",
                timestamp="2024-01-15T10:30:00Z",
                session_id="abc123",
            ),
            HistoryEntry(
                url="https://example2.com",
                reason="test2",
                type="convergent",
                feedback="liked",
                timestamp="2024-01-15T10:31:00Z",
                session_id="abc123",
            ),
        ]
        storage.append_history(entries)

        # Mark one as extracted
        count = storage.mark_extracted(["https://example1.com"])
        assert count == 1

        # Verify
        all_entries = storage.load_all_history()
        assert all_entries[0].extracted is True
        assert all_entries[1].extracted is False

    def test_mark_extracted_multiple(self, storage):
        """Test marking multiple entries as extracted."""
        entries = [
            HistoryEntry(
                url=f"https://example{i}.com",
                reason=f"test{i}",
                type="convergent",
                feedback="liked",
                timestamp="2024-01-15T10:30:00Z",
                session_id="abc123",
            )
            for i in range(5)
        ]
        storage.append_history(entries)

        # Mark 3 as extracted
        urls = ["https://example0.com", "https://example2.com", "https://example4.com"]
        count = storage.mark_extracted(urls)
        assert count == 3

        all_entries = storage.load_all_history()
        assert all_entries[0].extracted is True
        assert all_entries[1].extracted is False
        assert all_entries[2].extracted is True
        assert all_entries[3].extracted is False
        assert all_entries[4].extracted is True

    def test_get_unextracted_entries(self, storage):
        """Test getting unextracted entries."""
        entries = [
            HistoryEntry(
                url="https://example1.com",
                reason="test1",
                type="convergent",
                feedback="liked",
                timestamp="2024-01-15T10:30:00Z",
                session_id="abc123",
                extracted=True,
            ),
            HistoryEntry(
                url="https://example2.com",
                reason="test2",
                type="convergent",
                feedback="liked",
                timestamp="2024-01-15T10:31:00Z",
                session_id="abc123",
                extracted=False,
            ),
        ]
        storage.append_history(entries)

        unextracted = storage.get_unextracted_entries()
        assert len(unextracted) == 1
        assert unextracted[0].url == "https://example2.com"

    def test_get_unextracted_entries_by_feedback(self, storage):
        """Test getting unextracted entries filtered by feedback."""
        entries = [
            HistoryEntry(
                url="https://liked1.com",
                reason="test",
                type="convergent",
                feedback="liked",
                timestamp="2024-01-15T10:30:00Z",
                session_id="abc123",
            ),
            HistoryEntry(
                url="https://disliked1.com",
                reason="test",
                type="divergent",
                feedback="disliked",
                timestamp="2024-01-15T10:31:00Z",
                session_id="abc123",
            ),
            HistoryEntry(
                url="https://liked2.com",
                reason="test",
                type="convergent",
                feedback="liked",
                timestamp="2024-01-15T10:32:00Z",
                session_id="abc123",
            ),
        ]
        storage.append_history(entries)

        liked = storage.get_unextracted_entries("liked")
        assert len(liked) == 2

        disliked = storage.get_unextracted_entries("disliked")
        assert len(disliked) == 1

    def test_build_history_context_with_rules(self, storage):
        """Test that build_history_context includes rules."""
        storage.append_rule("Japanese Minimalism", "I like clean designs.", "like")

        context = storage.build_history_context()
        assert "<discovery_rules>" in context
        assert "Japanese Minimalism" in context

    def test_build_history_context_filters_extracted(self, storage):
        """Test that build_history_context excludes extracted items."""
        entries = [
            HistoryEntry(
                url="https://extracted.com",
                reason="extracted item",
                type="convergent",
                feedback="liked",
                timestamp="2024-01-15T10:30:00Z",
                session_id="abc123",
                extracted=True,
            ),
            HistoryEntry(
                url="https://unextracted.com",
                reason="unextracted item",
                type="convergent",
                feedback="liked",
                timestamp="2024-01-15T10:31:00Z",
                session_id="abc123",
                extracted=False,
            ),
        ]
        storage.append_history(entries)

        context = storage.build_history_context()
        # Unextracted should be in "Items you've liked (not yet in rules)"
        assert "https://unextracted.com" in context
        # Extracted should NOT be in the liked section (but may be in recent)
        # Check that it's not in the "not yet in rules" section
        assert "extracted item" not in context or "not yet in rules" not in context.split("extracted.com")[0]


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_values(self):
        """Test default config values."""
        config = Config()
        assert config.preferences_path == "~/.serendipity/preferences.md"
        assert config.history_enabled is True
        assert config.default_model == "opus"

    def test_to_dict(self):
        """Test config serialization."""
        config = Config()
        d = config.to_dict()
        assert "preferences_path" in d
        assert "history_enabled" in d

    def test_from_dict(self):
        """Test config deserialization."""
        d = {
            "preferences_path": "/custom/path.md",
            "history_enabled": False,
            "default_model": "haiku",
        }
        config = Config.from_dict(d)
        assert config.preferences_path == "/custom/path.md"
        assert config.history_enabled is False
        assert config.default_model == "haiku"
