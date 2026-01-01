"""Tests for serendipity CLI."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from serendipity.cli import app
from serendipity.storage import HistoryEntry, StorageManager

runner = CliRunner()


class TestLearningsCommand:
    """Tests for the learnings command (via profile get learnings)."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            # Create default settings so TypesConfig works
            from serendipity.config.types import TypesConfig
            TypesConfig.write_defaults(storage.settings_path)
            yield storage, Path(tmpdir)

    def test_learnings_show_empty(self, temp_storage):
        """Test showing learnings when none exist."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "get", "learnings"])
            assert result.exit_code == 0
            assert "No learnings yet" in result.stdout

    def test_learnings_show_with_learnings(self, temp_storage):
        """Test showing learnings when they exist."""
        storage, tmpdir = temp_storage
        storage.append_learning("Test Learning", "This is a test learning.", "like")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "get", "learnings"])
            assert result.exit_code == 0
            assert "Test Learning" in result.stdout

    def test_learnings_clear_cancelled(self, temp_storage):
        """Test cancelling learnings clear."""
        storage, tmpdir = temp_storage
        storage.append_learning("Test Learning", "Content", "like")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "get", "learnings", "--clear"], input="n\n")
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
            result = runner.invoke(app, ["profile", "get", "learnings", "--clear"], input="y\n")
            assert result.exit_code == 0
            assert "cleared" in result.stdout.lower()
            # Learning should be gone
            assert storage.load_learnings() == ""

    def test_learnings_help(self):
        """Test profile get command help (includes learnings options)."""
        result = runner.invoke(app, ["profile", "get", "--help"])
        assert result.exit_code == 0
        assert "interactive" in result.stdout.lower()
        assert "clear" in result.stdout.lower()


class TestHistoryCommand:
    """Tests for the history command (via profile get history)."""

    @pytest.fixture
    def temp_storage_with_history(self):
        """Create a temporary storage with some history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            # Create default settings so TypesConfig works
            from serendipity.config.types import TypesConfig
            TypesConfig.write_defaults(storage.settings_path)
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
            result = runner.invoke(app, ["profile", "get", "history"])
            assert result.exit_code == 0
            assert "example1.com" in result.stdout
            assert "example2.com" in result.stdout

    def test_history_liked(self, temp_storage_with_history):
        """Test showing only liked items."""
        storage, tmpdir = temp_storage_with_history
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "get", "history", "--liked"])
            assert result.exit_code == 0
            assert "example1.com" in result.stdout
            assert "example2.com" not in result.stdout

    def test_history_disliked(self, temp_storage_with_history):
        """Test showing only disliked items."""
        storage, tmpdir = temp_storage_with_history
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "get", "history", "--disliked"])
            assert result.exit_code == 0
            assert "example1.com" not in result.stdout
            assert "example2.com" in result.stdout


class TestSettingsCommand:
    """Tests for the settings command."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            yield storage, Path(tmpdir)

    def test_settings_show(self, temp_storage):
        """Test showing settings."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["settings"])
            assert result.exit_code == 0
            assert "model" in result.stdout
            assert "total_count" in result.stdout
            assert "Approaches" in result.stdout

    def test_settings_show_displays_all_sections(self, temp_storage):
        """Test that settings shows all configuration sections."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["settings"])
            assert result.exit_code == 0
            # Top-level settings
            assert "model" in result.stdout
            assert "total_count" in result.stdout
            assert "feedback_server_port" in result.stdout
            # Sections
            assert "Approaches" in result.stdout
            assert "Media Types" in result.stdout
            assert "Context Sources" in result.stdout
            # Default values
            assert "convergent" in result.stdout
            assert "divergent" in result.stdout

    def test_settings_reset(self, temp_storage):
        """Test resetting settings (with confirmation bypass)."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            # Create initial settings file
            from serendipity.config.types import TypesConfig
            TypesConfig.write_defaults(storage.settings_path)

            # Use input to bypass confirmation
            result = runner.invoke(app, ["settings", "--reset"], input="y\n")
            assert result.exit_code == 0
            assert "reset" in result.stdout.lower() or "Reset" in result.stdout

    def test_settings_reset_cancelled(self, temp_storage):
        """Test cancelling settings reset."""
        storage, tmpdir = temp_storage
        from serendipity.config.types import TypesConfig
        TypesConfig.write_defaults(storage.settings_path)

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["settings", "--reset"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.stdout

    def test_settings_enable_source(self, temp_storage):
        """Test enabling a context source."""
        storage, tmpdir = temp_storage
        from serendipity.config.types import TypesConfig
        TypesConfig.write_defaults(storage.settings_path)

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["settings", "--enable-source", "whorl"])
            assert result.exit_code == 0
            assert "Enabled" in result.stdout
            assert "whorl" in result.stdout

    def test_settings_disable_source(self, temp_storage):
        """Test disabling a context source."""
        storage, tmpdir = temp_storage
        from serendipity.config.types import TypesConfig
        TypesConfig.write_defaults(storage.settings_path)

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["settings", "--disable-source", "history"])
            assert result.exit_code == 0
            assert "Disabled" in result.stdout
            assert "history" in result.stdout

    def test_settings_enable_unknown_source(self, temp_storage):
        """Test enabling an unknown source shows error."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["settings", "--enable-source", "nonexistent"])
            assert result.exit_code == 1
            assert "Unknown source" in result.stdout

    def test_settings_preview(self, temp_storage):
        """Test preview shows generated prompt sections."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["settings", "--preview"])
            assert result.exit_code == 0
            assert "APPROACH TYPES" in result.stdout
            assert "MEDIA TYPES" in result.stdout
            assert "DISTRIBUTION" in result.stdout
            assert "OUTPUT FORMAT" in result.stdout


class TestTasteCommand:
    """Tests for the taste command (via profile get taste)."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            # Create default settings so TypesConfig works
            from serendipity.config.types import TypesConfig
            TypesConfig.write_defaults(storage.settings_path)
            yield storage, Path(tmpdir)

    def test_taste_show_empty(self, temp_storage):
        """Test showing taste when none exist."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "get", "taste"])
            assert result.exit_code == 0
            # Shows "file not found" or empty message
            assert result.exit_code == 0

    def test_taste_show_with_content(self, temp_storage):
        """Test showing taste when it exists."""
        storage, tmpdir = temp_storage
        # Write taste directly to file at the configured path
        storage.taste_path.write_text("# My Taste\n\nI like minimalism.")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            # Also patch is_source_editable to return the temp path
            with patch("serendipity.cli.is_source_editable") as mock_editable:
                mock_editable.return_value = (True, storage.taste_path)
                result = runner.invoke(app, ["profile", "get", "taste"])
                assert result.exit_code == 0
                assert "minimalism" in result.stdout


class TestProfileCommand:
    """Tests for the profile command."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            yield storage, Path(tmpdir)

    def test_profile_enable_source(self, temp_storage):
        """Test enabling a source via profile command."""
        storage, tmpdir = temp_storage
        from serendipity.config.types import TypesConfig
        TypesConfig.write_defaults(storage.settings_path)

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "--enable-source", "whorl"])
            assert result.exit_code == 0
            assert "Enabled" in result.stdout
            assert "whorl" in result.stdout

    def test_profile_disable_source(self, temp_storage):
        """Test disabling a source via profile command."""
        storage, tmpdir = temp_storage
        from serendipity.config.types import TypesConfig
        TypesConfig.write_defaults(storage.settings_path)

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "--disable-source", "taste"])
            assert result.exit_code == 0
            assert "Disabled" in result.stdout
            assert "taste" in result.stdout

    def test_profile_enable_unknown_source(self, temp_storage):
        """Test enabling an unknown source shows error."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "--enable-source", "nonexistent"])
            assert result.exit_code == 1
            assert "Unknown source" in result.stdout

    def test_profile_help_shows_new_flags(self):
        """Test profile --help shows the new flags."""
        result = runner.invoke(app, ["profile", "--help"])
        assert result.exit_code == 0
        assert "--enable-source" in result.stdout
        assert "--disable-source" in result.stdout
        assert "--interactive" in result.stdout or "-i" in result.stdout


class TestMainCommand:
    """Tests for the main app behavior."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
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
        assert "settings" in result.stdout
        assert "profile" in result.stdout  # Now uses profile subcommand group


class TestSurpriseMeMode:
    """Tests for the 'surprise me' mode (no-input discover)."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
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


class TestDiscoverCommand:
    """Tests for the discover command."""

    @pytest.fixture
    def temp_storage_with_profile(self):
        """Create a temporary storage with taste profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            # Create taste profile to bypass onboarding
            storage.taste_path.write_text("# My Taste\n\nI like minimalism.")
            yield storage, Path(tmpdir)

    def test_discover_help(self):
        """Test discover --help."""
        result = runner.invoke(app, ["discover", "--help"])
        assert result.exit_code == 0
        assert "context" in result.stdout.lower()
        assert "model" in result.stdout.lower()

    def test_discover_paste_flag_recognized(self):
        """Test that --paste flag is recognized in help."""
        result = runner.invoke(app, ["discover", "--help"])
        assert result.exit_code == 0
        assert "--paste" in result.stdout or "-p" in result.stdout

    def test_discover_verbose_flag_recognized(self):
        """Test that --verbose flag is recognized in help."""
        result = runner.invoke(app, ["discover", "--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.stdout or "-v" in result.stdout

    def test_discover_model_flag(self, temp_storage_with_profile):
        """Test that --model flag is recognized."""
        storage, tmpdir = temp_storage_with_profile
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            # Just verify the flag is recognized
            result = runner.invoke(app, ["discover", "--help"])
            assert "--model" in result.stdout

    def test_discover_shows_session_id(self, temp_storage_with_profile):
        """Test that discover command outputs session ID and resume command."""
        from serendipity.agent import DiscoveryResult
        from serendipity.models import Recommendation

        storage, tmpdir = temp_storage_with_profile

        # Create context file
        context_file = tmpdir / "context.txt"
        context_file.write_text("test context")

        # Create a mock discovery result with a session ID
        mock_result = DiscoveryResult(
            convergent=[Recommendation(url="https://example.com", reason="test", approach="convergent")],
            divergent=[],
            session_id="test-session-123",
            cost_usd=0.01,
            html_path=tmpdir / "output" / "test.html",
        )

        # Ensure HTML file exists
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "test.html").write_text("<html></html>")

        with patch("serendipity.cli.StorageManager") as mock_cls, \
             patch("serendipity.cli.SerendipityAgent") as mock_agent_cls, \
             patch("serendipity.cli.ContextSourceManager") as mock_ctx_cls:
            mock_cls.return_value = storage
            mock_agent = MagicMock()
            mock_agent.run_sync.return_value = mock_result
            mock_agent.output_dir = output_dir
            mock_agent_cls.return_value = mock_agent
            mock_ctx_manager = MagicMock()
            mock_ctx_manager.get_enabled_source_names.return_value = []
            mock_ctx_manager.get_mcp_servers.return_value = {}
            mock_ctx_manager.get_allowed_tools.return_value = ["WebSearch", "WebFetch"]
            mock_ctx_manager.sources = {}

            async def mock_init(*args, **kwargs):
                return []
            async def mock_build_context(*args, **kwargs):
                return ("", [])

            mock_ctx_manager.initialize = mock_init
            mock_ctx_manager.build_context = mock_build_context
            mock_ctx_cls.return_value = mock_ctx_manager

            result = runner.invoke(app, ["discover", "-o", "terminal", str(context_file)])

            # Verify session info is shown
            assert "Session:" in result.stdout or "test-session-123" in result.stdout
            assert "claude -r test-session-123" in result.stdout


class TestCLIIntegration:
    """Integration tests for CLI flows."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            yield storage, Path(tmpdir)

    def test_full_profile_flow(self, temp_storage):
        """Test profile subcommand navigation."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage

            # Check profile help - now shows generic get/edit commands
            result = runner.invoke(app, ["profile", "--help"])
            assert result.exit_code == 0
            assert "get" in result.stdout
            assert "edit" in result.stdout

    def test_settings_and_profile_source_sync(self, temp_storage):
        """Test that settings and profile share source enable/disable."""
        storage, tmpdir = temp_storage
        from serendipity.config.types import TypesConfig
        TypesConfig.write_defaults(storage.settings_path)

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage

            # Enable via settings
            result = runner.invoke(app, ["settings", "--enable-source", "whorl"])
            assert result.exit_code == 0
            assert "Enabled" in result.stdout

            # Check it's enabled
            config = TypesConfig.from_yaml(storage.settings_path)
            assert config.context_sources["whorl"].enabled is True


class TestSettingsAddCommand:
    """Tests for the settings add command."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(base_dir=Path(tmpdir))
            storage.ensure_dirs()
            yield storage, Path(tmpdir)

    def test_settings_add_help(self, temp_storage):
        """Test settings add help displays correctly."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["settings", "add", "--help"])
            assert result.exit_code == 0
            assert "media" in result.stdout
            assert "approach" in result.stdout
            assert "source" in result.stdout
            assert "--name" in result.stdout
            assert "--display" in result.stdout
            assert "--interactive" in result.stdout

    def test_settings_add_media(self, temp_storage):
        """Test adding a media type."""
        storage, tmpdir = temp_storage
        from serendipity import settings as settings_module

        # Patch settings_module to use temp storage
        with patch.object(
            settings_module,
            "get_user_settings_path",
            return_value=storage.settings_path
        ):
            result = runner.invoke(
                app,
                ["settings", "add", "media", "-n", "papers", "-d", "Academic Papers"]
            )
            assert result.exit_code == 0
            assert "Added media type" in result.stdout
            assert "papers" in result.stdout

    def test_settings_add_approach(self, temp_storage):
        """Test adding an approach type."""
        storage, tmpdir = temp_storage
        from serendipity import settings as settings_module

        with patch.object(
            settings_module,
            "get_user_settings_path",
            return_value=storage.settings_path
        ):
            result = runner.invoke(
                app,
                ["settings", "add", "approach", "-n", "lucky", "-d", "Pure Luck"]
            )
            assert result.exit_code == 0
            assert "Added approach" in result.stdout
            assert "lucky" in result.stdout

    def test_settings_add_loader_source(self, temp_storage):
        """Test adding a loader source."""
        storage, tmpdir = temp_storage
        from serendipity import settings as settings_module

        with patch.object(
            settings_module,
            "get_user_settings_path",
            return_value=storage.settings_path
        ):
            result = runner.invoke(
                app,
                ["settings", "add", "source", "-n", "notes", "-t", "loader", "--path", "~/notes.md"]
            )
            assert result.exit_code == 0
            assert "Added loader source" in result.stdout
            assert "notes" in result.stdout

    def test_settings_add_mcp_source(self, temp_storage):
        """Test adding an MCP source."""
        storage, tmpdir = temp_storage
        from serendipity import settings as settings_module

        with patch.object(
            settings_module,
            "get_user_settings_path",
            return_value=storage.settings_path
        ):
            result = runner.invoke(
                app,
                ["settings", "add", "source", "-n", "custom", "-t", "mcp"]
            )
            assert result.exit_code == 0
            assert "Added mcp source" in result.stdout
            assert "custom" in result.stdout

    def test_settings_add_invalid_type(self, temp_storage):
        """Test error on invalid type."""
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(
                app,
                ["settings", "add", "invalid", "-n", "test"]
            )
            assert result.exit_code == 1
            assert "Unknown type" in result.stdout

    def test_settings_add_source_requires_type(self, temp_storage):
        """Test that source requires --type flag."""
        storage, tmpdir = temp_storage
        from serendipity import settings as settings_module

        with patch.object(
            settings_module,
            "get_user_settings_path",
            return_value=storage.settings_path
        ):
            result = runner.invoke(
                app,
                ["settings", "add", "source", "-n", "test"]
            )
            assert result.exit_code == 1
            assert "Source type required" in result.stdout

    def test_settings_add_loader_requires_path(self, temp_storage):
        """Test that loader source requires --path flag."""
        storage, tmpdir = temp_storage
        from serendipity import settings as settings_module

        with patch.object(
            settings_module,
            "get_user_settings_path",
            return_value=storage.settings_path
        ):
            result = runner.invoke(
                app,
                ["settings", "add", "source", "-n", "test", "-t", "loader"]
            )
            assert result.exit_code == 1
            assert "Path required" in result.stdout


