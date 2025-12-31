"""Tests for serendipity storage module."""

import json
import tempfile
from pathlib import Path

import pytest

from serendipity.storage import HistoryEntry, StorageManager


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

    def test_learnings_path(self, storage, temp_dir):
        """Test learnings_path property."""
        assert storage.learnings_path == temp_dir / "learnings.md"

    def test_load_learnings_empty(self, storage):
        """Test loading learnings when file doesn't exist."""
        learnings = storage.load_learnings()
        assert learnings == ""

    def test_save_and_load_learnings(self, storage):
        """Test saving and loading learnings."""
        content = "# My Learnings\n\n## Likes\n\n### Test Learning\nContent here."
        storage.save_learnings(content)
        loaded = storage.load_learnings()
        assert loaded == content

    def test_append_learning_to_empty(self, storage):
        """Test appending a learning when no learnings exist."""
        storage.append_learning("Japanese Minimalism", "I like clean designs.", "like")
        learnings = storage.load_learnings()
        assert "# My Discovery Learnings" in learnings
        assert "## Likes" in learnings
        assert "### Japanese Minimalism" in learnings
        assert "I like clean designs." in learnings

    def test_append_learning_to_existing(self, storage):
        """Test appending a learning to existing learnings."""
        storage.append_learning("First Learning", "Content 1", "like")
        storage.append_learning("Second Learning", "Content 2", "like")
        learnings = storage.load_learnings()
        assert "### First Learning" in learnings
        assert "### Second Learning" in learnings

    def test_append_dislike_learning(self, storage):
        """Test appending a dislike learning."""
        storage.append_learning("Clickbait", "I don't like clickbait.", "dislike")
        learnings = storage.load_learnings()
        assert "## Dislikes" in learnings
        assert "### Clickbait" in learnings

    def test_clear_learnings(self, storage):
        """Test clearing learnings."""
        storage.append_learning("Test", "Content", "like")
        assert storage.load_learnings() != ""
        storage.clear_learnings()
        assert storage.load_learnings() == ""

    def test_load_taste_empty(self, storage, temp_dir):
        """Test loading taste when file doesn't exist."""
        taste = storage.load_taste()
        assert taste == ""

    def test_taste_path(self, storage, temp_dir):
        """Test taste_path property."""
        assert storage.taste_path == temp_dir / "taste.md"

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

    def test_build_history_context_with_learnings(self, storage):
        """Test that build_history_context includes learnings."""
        storage.append_learning("Japanese Minimalism", "I like clean designs.", "like")

        context = storage.build_history_context()
        assert "<discovery_learnings>" in context
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
        # Unextracted should be in "Items you've liked (not yet in learnings)"
        assert "https://unextracted.com" in context
        # Extracted should NOT be in the liked section (but may be in recent)
        # Check that it's not in the "not yet in learnings" section
        assert "extracted item" not in context or "not yet in learnings" not in context.split("extracted.com")[0]


class TestMigration:
    """Tests for file migration logic."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_migrate_preferences_to_taste(self, temp_dir):
        """Test migrating preferences.md to taste.md."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()

        # Create old preferences file
        old_file = temp_dir / "preferences.md"
        old_file.write_text("# My Old Preferences")

        migrations = storage.migrate_if_needed()

        assert "preferences.md → taste.md" in migrations[0]
        assert not old_file.exists()
        assert (temp_dir / "taste.md").exists()
        assert (temp_dir / "taste.md").read_text() == "# My Old Preferences"

    def test_migrate_rules_to_learnings(self, temp_dir):
        """Test migrating rules.md to learnings.md."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()

        # Create old rules file
        old_file = temp_dir / "rules.md"
        old_file.write_text("# My Old Rules")

        migrations = storage.migrate_if_needed()

        assert "rules.md → learnings.md" in migrations[0]
        assert not old_file.exists()
        assert (temp_dir / "learnings.md").exists()

    def test_migrate_types_to_settings(self, temp_dir):
        """Test migrating types.yaml to settings.yaml."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()

        # Create old types.yaml file
        old_file = temp_dir / "types.yaml"
        old_file.write_text("version: 2\napproaches: {}")

        migrations = storage.migrate_if_needed()

        assert any("types.yaml → settings.yaml" in m for m in migrations)
        assert not old_file.exists()
        assert (temp_dir / "settings.yaml").exists()

    def test_remove_old_config_json(self, temp_dir):
        """Test that old config.json is removed."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()

        # Create old config.json
        old_file = temp_dir / "config.json"
        old_file.write_text('{"default_model": "opus"}')

        migrations = storage.migrate_if_needed()

        assert any("config.json" in m for m in migrations)
        assert not old_file.exists()

    def test_no_migration_when_new_files_exist(self, temp_dir):
        """Test that migration doesn't overwrite existing new files."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()

        # Create both old and new files
        (temp_dir / "preferences.md").write_text("Old content")
        (temp_dir / "taste.md").write_text("New content")

        migrations = storage.migrate_if_needed()

        # Should not migrate since new file exists
        assert len(migrations) == 0
        assert (temp_dir / "taste.md").read_text() == "New content"

    def test_no_migration_when_nothing_to_migrate(self, temp_dir):
        """Test that migration returns empty when nothing to do."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()

        migrations = storage.migrate_if_needed()

        assert migrations == []
