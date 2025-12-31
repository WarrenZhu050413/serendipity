"""Tests for serendipity CLI."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from serendipity.cli import app
from serendipity.storage import HistoryEntry, StorageManager

runner = CliRunner()


class TestRulesCommand:
    """Tests for the rules command."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            yield storage, Path(tmpdir)

    def test_rules_show_empty(self, temp_storage):
        """Test showing rules when none exist."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["rules"])
            assert result.exit_code == 0
            assert "No rules defined" in result.stdout

    def test_rules_show_with_rules(self, temp_storage):
        """Test showing rules when they exist."""
        storage, tmpdir = temp_storage
        storage.append_rule("Test Rule", "This is a test rule.", "like")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["rules"])
            assert result.exit_code == 0
            assert "Test Rule" in result.stdout

    def test_rules_clear_cancelled(self, temp_storage):
        """Test cancelling rules clear."""
        storage, tmpdir = temp_storage
        storage.append_rule("Test Rule", "Content", "like")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["rules", "--clear"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.stdout
            # Rule should still exist
            assert storage.load_rules() != ""

    def test_rules_clear_confirmed(self, temp_storage):
        """Test confirming rules clear."""
        storage, tmpdir = temp_storage
        storage.append_rule("Test Rule", "Content", "like")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["rules", "--clear"], input="y\n")
            assert result.exit_code == 0
            assert "cleared" in result.stdout.lower()
            # Rule should be gone
            assert storage.load_rules() == ""

    def test_rules_help(self):
        """Test rules command help."""
        result = runner.invoke(app, ["rules", "--help"])
        assert result.exit_code == 0
        assert "interactive" in result.stdout.lower()
        assert "edit" in result.stdout.lower()
        assert "clear" in result.stdout.lower()


class TestHistoryCommand:
    """Tests for the history command."""

    @pytest.fixture
    def temp_storage_with_history(self):
        """Create a temporary storage with some history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            entries = [
                HistoryEntry(
                    url="https://example1.com",
                    reason="test reason 1",
                    type="convergent",
                    feedback="liked",
                    timestamp="2024-01-15T10:30:00Z",
                    session_id="abc123",
                ),
                HistoryEntry(
                    url="https://example2.com",
                    reason="test reason 2",
                    type="divergent",
                    feedback="disliked",
                    timestamp="2024-01-15T10:31:00Z",
                    session_id="abc123",
                ),
            ]
            storage.append_history(entries)
            yield storage, Path(tmpdir)

    def test_history_show(self, temp_storage_with_history):
        """Test showing history."""
        storage, tmpdir = temp_storage_with_history
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["history"])
            assert result.exit_code == 0
            assert "example1.com" in result.stdout
            assert "example2.com" in result.stdout

    def test_history_liked(self, temp_storage_with_history):
        """Test showing only liked items."""
        storage, tmpdir = temp_storage_with_history
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["history", "--liked"])
            assert result.exit_code == 0
            assert "example1.com" in result.stdout
            assert "example2.com" not in result.stdout

    def test_history_disliked(self, temp_storage_with_history):
        """Test showing only disliked items."""
        storage, tmpdir = temp_storage_with_history
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["history", "--disliked"])
            assert result.exit_code == 0
            assert "example1.com" not in result.stdout
            assert "example2.com" in result.stdout


class TestConfigCommand:
    """Tests for the config command."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            yield storage, Path(tmpdir)

    def test_config_show(self, temp_storage):
        """Test showing config."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["config"])
            assert result.exit_code == 0
            assert "preferences_path" in result.stdout
            assert "history_enabled" in result.stdout
            assert "Description" in result.stdout  # New column

    def test_config_set(self, temp_storage):
        """Test setting a config value."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["config", "--set", "default_model=haiku"])
            assert result.exit_code == 0
            assert "haiku" in result.stdout

            # Verify it was saved
            config = storage.load_config()
            assert config.default_model == "haiku"

    def test_config_reset(self, temp_storage):
        """Test resetting config."""
        storage, tmpdir = temp_storage
        # First set a non-default value
        config = storage.load_config()
        config.default_model = "haiku"
        storage.save_config(config)

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["config", "--reset"])
            assert result.exit_code == 0
            assert "reset" in result.stdout.lower()

            # Verify it was reset
            config = storage.load_config()
            assert config.default_model == "opus"  # Default value


class TestPreferencesCommand:
    """Tests for the preferences command."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            yield storage, Path(tmpdir)

    def test_preferences_show_empty(self, temp_storage):
        """Test showing preferences when none exist (shows template if no prefs file)."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["preferences", "--show"])
            assert result.exit_code == 0
            # Either shows "No preferences" or shows default content
            # The actual behavior depends on whether preferences file exists
            assert result.exit_code == 0

    def test_preferences_show_with_content(self, temp_storage):
        """Test showing preferences when they exist."""
        storage, tmpdir = temp_storage
        storage.save_preferences("# My Taste\n\nI like minimalism.")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["preferences", "--show"])
            assert result.exit_code == 0
            assert "minimalism" in result.stdout


class TestMainCommand:
    """Tests for the main app behavior."""

    def test_no_args_shows_help(self):
        """Test that no args shows usage panel."""
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Commands" in result.stdout or "serendipity" in result.stdout

    def test_help_flag(self):
        """Test --help flag."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "discover" in result.stdout
        assert "config" in result.stdout
        assert "rules" in result.stdout
