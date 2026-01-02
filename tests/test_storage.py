"""Tests for serendipity storage module."""

import json
import tempfile
from pathlib import Path

import pytest

from serendipity.storage import HistoryEntry, ProfileManager, StorageManager


class TestHistoryEntry:
    """Tests for HistoryEntry dataclass."""

    def test_create_entry(self):
        """Test creating a basic history entry."""
        entry = HistoryEntry(
            url="https://example.com",
            reason="Great content",
            type="convergent",
            rating=4,
            timestamp="2024-01-15T10:30:00Z",
            session_id="abc123",
        )
        assert entry.url == "https://example.com"
        assert entry.rating == 4
        assert entry.feedback == "liked"  # Backward compat property
        assert entry.extracted is False  # Default value

    def test_extracted_field_default(self):
        """Test that extracted defaults to False."""
        entry = HistoryEntry(
            url="https://example.com",
            reason="test",
            type="convergent",
            rating=None,
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
            rating=4,
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
            rating=4,
            timestamp="2024-01-15T10:30:00Z",
            session_id="abc123",
            extracted=True,
        )
        d = entry.to_dict()
        assert d["url"] == "https://example.com"
        assert d["rating"] == 4
        assert d["extracted"] is True
        assert "extracted" in d

    def test_from_dict(self):
        """Test deserializing from dictionary with rating."""
        d = {
            "url": "https://example.com",
            "reason": "Great content",
            "type": "convergent",
            "rating": 4,
            "timestamp": "2024-01-15T10:30:00Z",
            "session_id": "abc123",
            "extracted": True,
        }
        entry = HistoryEntry.from_dict(d)
        assert entry.url == "https://example.com"
        assert entry.rating == 4
        assert entry.extracted is True

    def test_from_dict_legacy_feedback_liked(self):
        """Test deserializing from old feedback='liked' format (migrates to rating=4)."""
        d = {
            "url": "https://example.com",
            "reason": "Great content",
            "type": "convergent",
            "feedback": "liked",
            "timestamp": "2024-01-15T10:30:00Z",
            "session_id": "abc123",
        }
        entry = HistoryEntry.from_dict(d)
        assert entry.rating == 4  # Migrated from "liked"
        assert entry.feedback == "liked"  # Backward compat property

    def test_from_dict_legacy_feedback_disliked(self):
        """Test deserializing from old feedback='disliked' format (migrates to rating=2)."""
        d = {
            "url": "https://example.com",
            "reason": "Great content",
            "type": "convergent",
            "feedback": "disliked",
            "timestamp": "2024-01-15T10:30:00Z",
            "session_id": "abc123",
        }
        entry = HistoryEntry.from_dict(d)
        assert entry.rating == 2  # Migrated from "disliked"
        assert entry.feedback == "disliked"  # Backward compat property

    def test_from_dict_missing_extracted(self):
        """Test deserializing from dict without extracted field (backwards compat)."""
        d = {
            "url": "https://example.com",
            "reason": "Great content",
            "type": "convergent",
            "rating": 5,
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
        assert storage.learnings_path == temp_dir / "user_data" / "learnings.md"

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
        assert storage.taste_path == temp_dir / "user_data" / "taste.md"

    def test_mark_extracted(self, storage):
        """Test marking entries as extracted."""
        entries = [
            HistoryEntry(
                url="https://example1.com",
                reason="test1",
                type="convergent",
                rating=4,
                timestamp="2024-01-15T10:30:00Z",
                session_id="abc123",
            ),
            HistoryEntry(
                url="https://example2.com",
                reason="test2",
                type="convergent",
                rating=4,
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
                rating=4,
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
                rating=4,
                timestamp="2024-01-15T10:30:00Z",
                session_id="abc123",
                extracted=True,
            ),
            HistoryEntry(
                url="https://example2.com",
                reason="test2",
                type="convergent",
                rating=4,
                timestamp="2024-01-15T10:31:00Z",
                session_id="abc123",
                extracted=False,
            ),
        ]
        storage.append_history(entries)

        unextracted = storage.get_unextracted_entries()
        assert len(unextracted) == 1
        assert unextracted[0].url == "https://example2.com"

    def test_get_unextracted_entries_by_rating(self, storage):
        """Test getting unextracted entries filtered by rating."""
        entries = [
            HistoryEntry(
                url="https://liked1.com",
                reason="test",
                type="convergent",
                rating=4,
                timestamp="2024-01-15T10:30:00Z",
                session_id="abc123",
            ),
            HistoryEntry(
                url="https://disliked1.com",
                reason="test",
                type="divergent",
                rating=2,
                timestamp="2024-01-15T10:31:00Z",
                session_id="abc123",
            ),
            HistoryEntry(
                url="https://loved1.com",
                reason="test",
                type="convergent",
                rating=5,
                timestamp="2024-01-15T10:32:00Z",
                session_id="abc123",
            ),
        ]
        storage.append_history(entries)

        # Get positive ratings (4-5)
        positive = storage.get_unextracted_entries(min_rating=4)
        assert len(positive) == 2

        # Get negative ratings (1-2)
        negative = storage.get_unextracted_entries(max_rating=2)
        assert len(negative) == 1

        # Get loved only (5)
        loved = storage.get_unextracted_entries(min_rating=5, max_rating=5)
        assert len(loved) == 1
        assert loved[0].url == "https://loved1.com"

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
                rating=4,
                timestamp="2024-01-15T10:30:00Z",
                session_id="abc123",
                extracted=True,
            ),
            HistoryEntry(
                url="https://unextracted.com",
                reason="unextracted item",
                type="convergent",
                rating=4,
                timestamp="2024-01-15T10:31:00Z",
                session_id="abc123",
                extracted=False,
            ),
        ]
        storage.append_history(entries)

        context = storage.build_history_context()
        # Unextracted should be in liked section
        assert "https://unextracted.com" in context
        # Extracted should NOT be in the liked section (but may be in recent)
        # Check that it's not in the "liked" section
        assert "extracted item" not in context or "Items you liked" not in context.split("extracted.com")[0]


class TestUpdateRating:
    """Tests for update_rating method."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def storage(self, temp_dir):
        """Create a StorageManager with temp directory."""
        return StorageManager(base_dir=temp_dir)

    def test_update_rating_no_history(self, storage):
        """Test updating rating when no history file exists."""
        result = storage.update_rating("https://example.com", "session123", 4)
        assert result is False

    def test_update_rating_entry_found(self, storage):
        """Test updating rating for an existing entry."""
        entries = [
            HistoryEntry(
                url="https://example.com",
                reason="test",
                type="convergent",
                rating=None,
                timestamp="2024-01-15T10:30:00Z",
                session_id="session123",
            ),
        ]
        storage.append_history(entries)

        result = storage.update_rating("https://example.com", "session123", 5)
        assert result is True

        # Verify the update
        loaded = storage.load_all_history()
        assert loaded[0].rating == 5

    def test_update_rating_entry_not_found(self, storage):
        """Test updating rating when entry doesn't exist."""
        entries = [
            HistoryEntry(
                url="https://other.com",
                reason="test",
                type="convergent",
                rating=None,
                timestamp="2024-01-15T10:30:00Z",
                session_id="session123",
            ),
        ]
        storage.append_history(entries)

        result = storage.update_rating("https://example.com", "session123", 4)
        assert result is False

    def test_update_rating_wrong_session(self, storage):
        """Test updating rating when session ID doesn't match."""
        entries = [
            HistoryEntry(
                url="https://example.com",
                reason="test",
                type="convergent",
                rating=None,
                timestamp="2024-01-15T10:30:00Z",
                session_id="session123",
            ),
        ]
        storage.append_history(entries)

        result = storage.update_rating("https://example.com", "wrong-session", 4)
        assert result is False

    def test_update_rating_validates_value(self, storage):
        """Test that update_rating validates rating value."""
        entries = [
            HistoryEntry(
                url="https://example.com",
                reason="test",
                type="convergent",
                rating=None,
                timestamp="2024-01-15T10:30:00Z",
                session_id="session123",
            ),
        ]
        storage.append_history(entries)

        # Invalid rating (0 is not a valid star count)
        with pytest.raises(ValueError, match="Invalid rating"):
            storage.update_rating("https://example.com", "session123", 0)


class TestClearHistory:
    """Tests for clear_history method."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def storage(self, temp_dir):
        """Create a StorageManager with temp directory."""
        return StorageManager(base_dir=temp_dir)

    def test_clear_history_with_entries(self, storage):
        """Test clearing history when entries exist."""
        entries = [
            HistoryEntry(
                url="https://example.com",
                reason="test",
                type="convergent",
                rating=4,
                timestamp="2024-01-15T10:30:00Z",
                session_id="session123",
            ),
        ]
        storage.append_history(entries)
        assert len(storage.load_all_history()) == 1

        storage.clear_history()
        assert len(storage.load_all_history()) == 0
        assert not storage.history_path.exists()

    def test_clear_history_empty(self, storage):
        """Test clearing history when no file exists."""
        storage.clear_history()  # Should not raise
        assert not storage.history_path.exists()


class TestBuildHistoryContextEdgeCases:
    """Tests for build_history_context edge cases."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def storage(self, temp_dir):
        """Create a StorageManager with temp directory."""
        return StorageManager(base_dir=temp_dir)

    def test_build_history_context_empty(self, storage):
        """Test build_history_context with no history or learnings."""
        context = storage.build_history_context()
        assert context == ""

    def test_build_history_context_with_disliked(self, storage):
        """Test build_history_context includes disliked entries."""
        entries = [
            HistoryEntry(
                url="https://disliked.com",
                reason="not my taste",
                type="divergent",
                rating=2,
                timestamp="2024-01-15T10:30:00Z",
                session_id="session123",
                extracted=False,
            ),
        ]
        storage.append_history(entries)

        context = storage.build_history_context()
        assert "https://disliked.com" in context
        assert "Items you didn't like" in context

    def test_build_history_context_warning_callback(self, storage):
        """Test that warning callback is called for large history."""
        # Create many entries with rating=5 (loved) to include reasons in output
        # The "loved" section includes reason text, which increases word count
        entries = []
        for i in range(500):
            entries.append(
                HistoryEntry(
                    url=f"https://example{i}.com",
                    reason="This is a long reason " * 20,  # ~80 words per entry
                    type="convergent",
                    rating=5,  # Use "loved" rating to include reason in output
                    timestamp="2024-01-15T10:30:00Z",
                    session_id="session123",
                    extracted=False,
                )
            )
        storage.append_history(entries)

        warnings = []
        context = storage.build_history_context(
            max_recent=500,
            warn_callback=lambda msg: warnings.append(msg)
        )

        # Should have triggered the warning
        assert len(warnings) == 1
        assert "words" in warnings[0]

    def test_build_history_context_mixed_ratings(self, storage):
        """Test build_history_context with liked and disliked entries."""
        entries = [
            HistoryEntry(
                url="https://liked.com",
                reason="great content",
                type="convergent",
                rating=4,
                timestamp="2024-01-15T10:30:00Z",
                session_id="session123",
                extracted=False,
            ),
            HistoryEntry(
                url="https://disliked.com",
                reason="not for me",
                type="divergent",
                rating=2,
                timestamp="2024-01-15T10:31:00Z",
                session_id="session123",
                extracted=False,
            ),
        ]
        storage.append_history(entries)

        context = storage.build_history_context()
        assert "https://liked.com" in context
        assert "https://disliked.com" in context
        assert "Items you liked" in context
        assert "Items you didn't like" in context

    def test_build_history_context_intensity_groupings(self, storage):
        """Test build_history_context groups by rating intensity."""
        entries = [
            HistoryEntry(
                url="https://loved.com",
                reason="amazing",
                type="convergent",
                rating=5,
                timestamp="2024-01-15T10:30:00Z",
                session_id="session123",
                extracted=False,
            ),
            HistoryEntry(
                url="https://liked.com",
                reason="good",
                type="convergent",
                rating=4,
                timestamp="2024-01-15T10:31:00Z",
                session_id="session123",
                extracted=False,
            ),
            HistoryEntry(
                url="https://hated.com",
                reason="terrible",
                type="divergent",
                rating=1,
                timestamp="2024-01-15T10:32:00Z",
                session_id="session123",
                extracted=False,
            ),
        ]
        storage.append_history(entries)

        context = storage.build_history_context()
        assert "https://loved.com" in context
        assert "https://liked.com" in context
        assert "https://hated.com" in context
        assert "Items you LOVED" in context
        assert "Items you liked" in context
        assert "Items you didn't like" in context


class TestMigration:
    """Tests for file migration logic."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_migrate_preferences_to_taste(self, temp_dir):
        """Test migrating preferences.md to taste.md in user_data/."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()

        # Create old preferences file
        old_file = temp_dir / "preferences.md"
        old_file.write_text("# My Old Preferences")

        migrations = storage.migrate_if_needed()

        assert "preferences.md → user_data/taste.md" in migrations[0]
        assert not old_file.exists()
        assert (temp_dir / "user_data" / "taste.md").exists()
        assert (temp_dir / "user_data" / "taste.md").read_text() == "# My Old Preferences"

    def test_migrate_rules_to_learnings(self, temp_dir):
        """Test migrating rules.md to learnings.md in user_data/."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()

        # Create old rules file
        old_file = temp_dir / "rules.md"
        old_file.write_text("# My Old Rules")

        migrations = storage.migrate_if_needed()

        assert "rules.md → user_data/learnings.md" in migrations[0]
        assert not old_file.exists()
        assert (temp_dir / "user_data" / "learnings.md").exists()

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

        # Create both old and new files (new file in user_data/)
        (temp_dir / "preferences.md").write_text("Old content")
        (temp_dir / "user_data" / "taste.md").write_text("New content")

        migrations = storage.migrate_if_needed()

        # Should not migrate since new file exists
        assert len(migrations) == 0
        assert (temp_dir / "user_data" / "taste.md").read_text() == "New content"

    def test_no_migration_when_nothing_to_migrate(self, temp_dir):
        """Test that migration returns empty when nothing to do."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()

        migrations = storage.migrate_if_needed()

        assert migrations == []


class TestProfileManager:
    """Tests for ProfileManager class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def pm(self, temp_dir):
        """Create a ProfileManager with temp directory."""
        return ProfileManager(root_dir=temp_dir)

    def test_list_profiles_empty(self, pm):
        """Test listing profiles when none exist."""
        profiles = pm.list_profiles()
        # Should return default in registry
        assert "default" in profiles

    def test_create_profile(self, pm):
        """Test creating a new profile."""
        path = pm.create_profile("test-profile")
        assert path.exists()
        assert (path / "loaders").exists()
        assert "test-profile" in pm.list_profiles()

    def test_create_profile_already_exists(self, pm):
        """Test creating a profile that already exists fails."""
        pm.create_profile("test-profile")
        with pytest.raises(ValueError, match="already exists"):
            pm.create_profile("test-profile")

    def test_create_profile_from_existing(self, pm):
        """Test copying from an existing profile."""
        # Create source profile with content
        source_path = pm.create_profile("source")
        (source_path / "taste.md").write_text("My taste")
        (source_path / "settings.yaml").write_text("version: 2")

        # Create new profile from source
        new_path = pm.create_profile("copy", from_profile="source")

        assert (new_path / "taste.md").read_text() == "My taste"
        assert (new_path / "settings.yaml").exists()

    def test_create_profile_from_nonexistent(self, pm):
        """Test copying from nonexistent profile fails."""
        with pytest.raises(ValueError, match="does not exist"):
            pm.create_profile("new", from_profile="nonexistent")

    def test_get_active_profile_default(self, pm):
        """Test getting active profile returns default."""
        assert pm.get_active_profile() == "default"

    def test_set_active_profile(self, pm):
        """Test switching active profile."""
        pm.create_profile("work")
        pm.set_active_profile("work")
        assert pm.get_active_profile() == "work"

    def test_set_active_profile_nonexistent(self, pm):
        """Test switching to nonexistent profile fails."""
        with pytest.raises(ValueError, match="does not exist"):
            pm.set_active_profile("nonexistent")

    def test_delete_profile(self, pm):
        """Test deleting a profile."""
        pm.create_profile("to-delete")
        assert pm.profile_exists("to-delete")

        pm.delete_profile("to-delete")
        assert not pm.profile_exists("to-delete")
        assert "to-delete" not in pm.list_profiles()

    def test_delete_profile_nonexistent(self, pm):
        """Test deleting nonexistent profile fails."""
        with pytest.raises(ValueError, match="does not exist"):
            pm.delete_profile("nonexistent")

    def test_delete_active_profile_fails(self, pm):
        """Test that deleting the active profile fails."""
        pm.create_profile("active-one")
        pm.set_active_profile("active-one")

        with pytest.raises(ValueError, match="Cannot delete active"):
            pm.delete_profile("active-one")

    def test_rename_profile(self, pm):
        """Test renaming a profile."""
        pm.create_profile("old-name")
        (pm.get_profile_path("old-name") / "taste.md").write_text("Content")

        pm.rename_profile("old-name", "new-name")

        assert not pm.profile_exists("old-name")
        assert pm.profile_exists("new-name")
        assert (pm.get_profile_path("new-name") / "taste.md").read_text() == "Content"

    def test_rename_active_profile_updates_registry(self, pm):
        """Test that renaming active profile updates registry."""
        pm.create_profile("current")
        pm.set_active_profile("current")

        pm.rename_profile("current", "renamed")

        assert pm.get_active_profile() == "renamed"

    def test_export_profile(self, pm, temp_dir):
        """Test exporting a profile to tar.gz."""
        # Create profile with content
        path = pm.create_profile("export-me")
        (path / "taste.md").write_text("My taste")
        (path / "learnings.md").write_text("My learnings")

        # Export
        output = temp_dir / "export.tar.gz"
        result = pm.export_profile("export-me", output)

        assert result == output
        assert output.exists()

    def test_import_profile(self, pm, temp_dir):
        """Test importing a profile from tar.gz."""
        # Create and export a profile
        path = pm.create_profile("to-export")
        (path / "taste.md").write_text("Imported taste")

        archive = temp_dir / "archive.tar.gz"
        pm.export_profile("to-export", archive)

        # Delete original
        pm.delete_profile("to-export")
        assert not pm.profile_exists("to-export")

        # Import
        imported_name = pm.import_profile(archive)

        assert imported_name == "to-export"
        assert pm.profile_exists("to-export")
        assert (pm.get_profile_path("to-export") / "taste.md").read_text() == "Imported taste"

    def test_import_profile_with_name_override(self, pm, temp_dir):
        """Test importing with a different name."""
        path = pm.create_profile("original")
        (path / "taste.md").write_text("Content")

        archive = temp_dir / "archive.tar.gz"
        pm.export_profile("original", archive)

        # Import with different name
        imported_name = pm.import_profile(archive, name="imported")

        assert imported_name == "imported"
        assert pm.profile_exists("imported")

    def test_import_profile_already_exists(self, pm, temp_dir):
        """Test importing fails if profile already exists."""
        path = pm.create_profile("existing")
        archive = temp_dir / "archive.tar.gz"
        pm.export_profile("existing", archive)

        with pytest.raises(ValueError, match="already exists"):
            pm.import_profile(archive)

    def test_ensure_default_profile(self, pm):
        """Test ensuring default profile exists."""
        pm.ensure_default_profile()
        assert pm.profile_exists("default")

    def test_env_var_override(self, pm, monkeypatch):
        """Test SERENDIPITY_PROFILE environment variable."""
        pm.create_profile("env-profile")
        monkeypatch.setenv("SERENDIPITY_PROFILE", "env-profile")

        assert pm.get_active_profile() == "env-profile"


class TestStorageManagerWithProfiles:
    """Tests for StorageManager with profile support."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_storage_uses_profile_directory(self, temp_dir):
        """Test that StorageManager uses profile-specific directory."""
        pm = ProfileManager(root_dir=temp_dir)
        pm.create_profile("test-profile")
        pm.set_active_profile("test-profile")

        storage = StorageManager(profile_manager=pm)

        assert storage.base_dir == pm.get_profile_path("test-profile")
        assert storage.profile_name == "test-profile"

    def test_storage_explicit_profile(self, temp_dir):
        """Test using explicit profile name."""
        pm = ProfileManager(root_dir=temp_dir)
        pm.create_profile("explicit")

        storage = StorageManager(profile="explicit", profile_manager=pm)

        assert storage.base_dir == pm.get_profile_path("explicit")

    def test_storage_explicit_base_dir_overrides(self, temp_dir):
        """Test that explicit base_dir overrides profile."""
        custom_dir = temp_dir / "custom"
        custom_dir.mkdir()

        storage = StorageManager(base_dir=custom_dir)

        assert storage.base_dir == custom_dir
        assert storage.profile_manager is None

    def test_load_config_with_variable_context(self, temp_dir):
        """Test that load_config expands template variables."""
        pm = ProfileManager(root_dir=temp_dir)
        pm.create_profile("test")
        pm.set_active_profile("test")

        storage = StorageManager(profile_manager=pm)

        # Write a settings.yaml with template variables
        settings_content = """
version: 2
context_sources:
  taste:
    type: loader
    enabled: true
    options:
      path: "{profile_dir}/taste.md"
"""
        storage.settings_path.parent.mkdir(parents=True, exist_ok=True)
        storage.settings_path.write_text(settings_content)

        config = storage.load_config()

        # Check that {profile_dir} was expanded
        taste_config = config.context_sources.get("taste")
        assert taste_config is not None
        expected_path = str(storage.base_dir) + "/taste.md"
        assert taste_config.raw_config["options"]["path"] == expected_path


class TestStyleManagement:
    """Tests for style.css management."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary directory for testing."""
        return tmp_path

    def test_style_path_property(self, temp_dir):
        """Test that style_path returns correct path."""
        storage = StorageManager(base_dir=temp_dir)
        assert storage.style_path == temp_dir / "style.css"

    def test_get_style_path_creates_file(self, temp_dir):
        """Test that get_style_path creates file from default."""
        storage = StorageManager(base_dir=temp_dir)
        default_css = "body { color: red; }"

        path = storage.get_style_path(default_css)

        assert path.exists()
        assert path.read_text() == default_css

    def test_get_style_path_returns_existing(self, temp_dir):
        """Test that get_style_path returns existing file without overwriting."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()

        # Create custom style
        custom_css = "body { color: blue; }"
        storage.style_path.write_text(custom_css)

        # get_style_path should not overwrite
        path = storage.get_style_path("body { color: red; }")

        assert path.read_text() == custom_css

    def test_style_is_customized_false_when_missing(self, temp_dir):
        """Test style_is_customized returns False when file doesn't exist."""
        storage = StorageManager(base_dir=temp_dir)
        default_css = "body { color: red; }"

        assert storage.style_is_customized(default_css) is False

    def test_style_is_customized_false_when_matches_default(self, temp_dir):
        """Test style_is_customized returns False when content matches default."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()
        default_css = "body { color: red; }"

        storage.style_path.write_text(default_css)

        assert storage.style_is_customized(default_css) is False

    def test_style_is_customized_true_when_different(self, temp_dir):
        """Test style_is_customized returns True when content differs."""
        storage = StorageManager(base_dir=temp_dir)
        storage.ensure_dirs()
        default_css = "body { color: red; }"

        storage.style_path.write_text("body { color: blue; }")

        assert storage.style_is_customized(default_css) is True


class TestPromptManagement:
    """Tests for prompt file management."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary directory for testing."""
        return tmp_path

    def test_prompts_dir_property(self, temp_dir):
        """Test that prompts_dir returns correct path."""
        storage = StorageManager(base_dir=temp_dir)
        assert storage.prompts_dir == temp_dir / "prompts"

    def test_get_prompt_path_creates_file(self, temp_dir):
        """Test that get_prompt_path creates file from default."""
        storage = StorageManager(base_dir=temp_dir)
        default_prompt = "You are a helpful assistant."

        path = storage.get_prompt_path("test.txt", default_prompt)

        assert path.exists()
        assert path.read_text() == default_prompt
        assert path.parent == storage.prompts_dir

    def test_get_prompt_path_returns_existing(self, temp_dir):
        """Test that get_prompt_path returns existing file without overwriting."""
        storage = StorageManager(base_dir=temp_dir)
        storage.prompts_dir.mkdir(parents=True, exist_ok=True)

        # Create custom prompt
        custom_prompt = "Custom instructions"
        (storage.prompts_dir / "test.txt").write_text(custom_prompt)

        # get_prompt_path should not overwrite
        path = storage.get_prompt_path("test.txt", "Default instructions")

        assert path.read_text() == custom_prompt

    def test_prompt_is_customized_false_when_missing(self, temp_dir):
        """Test prompt_is_customized returns False when file doesn't exist."""
        storage = StorageManager(base_dir=temp_dir)
        default_prompt = "Default instructions"

        assert storage.prompt_is_customized("test.txt", default_prompt) is False

    def test_prompt_is_customized_false_when_matches_default(self, temp_dir):
        """Test prompt_is_customized returns False when content matches default."""
        storage = StorageManager(base_dir=temp_dir)
        storage.prompts_dir.mkdir(parents=True, exist_ok=True)
        default_prompt = "Default instructions"

        (storage.prompts_dir / "test.txt").write_text(default_prompt)

        assert storage.prompt_is_customized("test.txt", default_prompt) is False

    def test_prompt_is_customized_true_when_different(self, temp_dir):
        """Test prompt_is_customized returns True when content differs."""
        storage = StorageManager(base_dir=temp_dir)
        storage.prompts_dir.mkdir(parents=True, exist_ok=True)
        default_prompt = "Default instructions"

        (storage.prompts_dir / "test.txt").write_text("Custom instructions")

        assert storage.prompt_is_customized("test.txt", default_prompt) is True
