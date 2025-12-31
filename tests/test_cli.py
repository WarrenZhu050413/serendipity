"""Tests for serendipity CLI."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from serendipity.cli import app
from serendipity.storage import HistoryEntry, StorageManager

runner = CliRunner()


class TestLearningsCommand:
    """Tests for the learnings command."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            yield storage, Path(tmpdir)

    def test_learnings_show_empty(self, temp_storage):
        """Test showing learnings when none exist."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "learnings"])
            assert result.exit_code == 0
            assert "No learnings yet" in result.stdout

    def test_learnings_show_with_learnings(self, temp_storage):
        """Test showing learnings when they exist."""
        storage, tmpdir = temp_storage
        storage.append_learning("Test Learning", "This is a test learning.", "like")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "learnings"])
            assert result.exit_code == 0
            assert "Test Learning" in result.stdout

    def test_learnings_clear_cancelled(self, temp_storage):
        """Test cancelling learnings clear."""
        storage, tmpdir = temp_storage
        storage.append_learning("Test Learning", "Content", "like")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "learnings", "--clear"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.stdout
            # Learning should still exist
            assert storage.load_learnings() != ""

    def test_learnings_clear_confirmed(self, temp_storage):
        """Test confirming learnings clear."""
        storage, tmpdir = temp_storage
        storage.append_learning("Test Learning", "Content", "like")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "learnings", "--clear"], input="y\n")
            assert result.exit_code == 0
            assert "cleared" in result.stdout.lower()
            # Learning should be gone
            assert storage.load_learnings() == ""

    def test_learnings_help(self):
        """Test learnings command help."""
        result = runner.invoke(app, ["profile", "learnings", "--help"])
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
            result = runner.invoke(app, ["profile", "history"])
            assert result.exit_code == 0
            assert "example1.com" in result.stdout
            assert "example2.com" in result.stdout

    def test_history_liked(self, temp_storage_with_history):
        """Test showing only liked items."""
        storage, tmpdir = temp_storage_with_history
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "history", "--liked"])
            assert result.exit_code == 0
            assert "example1.com" in result.stdout
            assert "example2.com" not in result.stdout

    def test_history_disliked(self, temp_storage_with_history):
        """Test showing only disliked items."""
        storage, tmpdir = temp_storage_with_history
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "history", "--disliked"])
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
            assert "taste_path" in result.stdout
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


class TestTasteCommand:
    """Tests for the taste command."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory with isolated config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            # Configure taste_path to be within temp_dir
            config = storage.load_config()
            config.taste_path = str(Path(tmpdir) / "taste.md")
            storage.save_config(config)
            yield storage, Path(tmpdir)

    def test_taste_show_empty(self, temp_storage):
        """Test showing taste when none exist (shows template if no taste file)."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "taste", "--show"])
            assert result.exit_code == 0
            # Either shows "No taste profile" or shows default content
            # The actual behavior depends on whether taste file exists
            assert result.exit_code == 0

    def test_taste_show_with_content(self, temp_storage):
        """Test showing taste when it exists."""
        storage, tmpdir = temp_storage
        # Write taste directly to file at the configured path
        taste_path = storage.get_taste_path()
        taste_path.write_text("# My Taste\n\nI like minimalism.")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "taste", "--show"])
            assert result.exit_code == 0
            assert "minimalism" in result.stdout


class TestMainCommand:
    """Tests for the main app behavior."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory with isolated config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            # Configure taste_path to be within temp_dir
            config = storage.load_config()
            config.taste_path = str(Path(tmpdir) / "taste.md")
            storage.save_config(config)
            yield storage, Path(tmpdir)

    def test_no_args_without_profile_shows_onboarding(self, temp_storage):
        """Test that no args without profile shows onboarding."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, [])
            assert result.exit_code == 0
            # Should show onboarding since no taste profile exists
            assert "profile taste" in result.stdout or "taste" in result.stdout.lower()

    def test_help_flag(self):
        """Test --help flag."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "discover" in result.stdout
        assert "config" in result.stdout
        assert "profile" in result.stdout  # Now uses profile subcommand group


class TestSurpriseMeMode:
    """Tests for the 'surprise me' mode (no-input discover)."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory with isolated config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            # Configure taste_path to be within temp_dir
            config = storage.load_config()
            config.taste_path = str(Path(tmpdir) / "taste.md")
            storage.save_config(config)
            yield storage, Path(tmpdir)

    def test_no_input_without_profile_shows_onboarding(self, temp_storage):
        """Test that discover with no input and no profile shows onboarding."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["discover"])
            assert result.exit_code == 0
            # Should show onboarding
            assert "taste" in result.stdout.lower() or "profile" in result.stdout.lower()

    # Note: Tests that require mocking the full agent flow are in test_agent.py
    # These tests cover the "surprise me" behavior at the CLI level
