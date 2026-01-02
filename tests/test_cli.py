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
    """Tests for the learnings command (via profile manage learnings)."""

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
            result = runner.invoke(app, ["profile", "manage", "learnings"])
            assert result.exit_code == 0
            assert "No learnings yet" in result.stdout

    def test_learnings_show_with_learnings(self, temp_storage):
        """Test showing learnings when they exist."""
        storage, tmpdir = temp_storage
        storage.append_learning("Test Learning", "This is a test learning.", "like")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "manage", "learnings"])
            assert result.exit_code == 0
            assert "Test Learning" in result.stdout

    def test_learnings_clear_cancelled(self, temp_storage):
        """Test cancelling learnings clear."""
        storage, tmpdir = temp_storage
        storage.append_learning("Test Learning", "Content", "like")

        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "manage", "learnings", "--clear"], input="n\n")
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
            result = runner.invoke(app, ["profile", "manage", "learnings", "--clear"], input="y\n")
            assert result.exit_code == 0
            assert "cleared" in result.stdout.lower()
            # Learning should be gone
            assert storage.load_learnings() == ""

    def test_learnings_help(self):
        """Test profile manage command help (includes learnings options)."""
        result = runner.invoke(app, ["profile", "manage", "--help"])
        assert result.exit_code == 0
        assert "interactive" in result.stdout.lower()
        assert "clear" in result.stdout.lower()


class TestHistoryCommand:
    """Tests for the history command (via profile manage history)."""

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
                    rating=4,
                    timestamp="2024-01-15T10:30:00Z",
                    session_id="abc123",
                ),
                HistoryEntry(
                    url="https://example2.com",
                    reason="test reason 2",
                    type="divergent",
                    rating=2,
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
            result = runner.invoke(app, ["profile", "manage", "history"])
            assert result.exit_code == 0
            assert "example1.com" in result.stdout
            assert "example2.com" in result.stdout

    def test_history_liked(self, temp_storage_with_history):
        """Test showing only liked items."""
        storage, tmpdir = temp_storage_with_history
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "manage", "history", "--liked"])
            assert result.exit_code == 0
            assert "example1.com" in result.stdout
            assert "example2.com" not in result.stdout

    def test_history_disliked(self, temp_storage_with_history):
        """Test showing only disliked items."""
        storage, tmpdir = temp_storage_with_history
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["profile", "manage", "history", "--disliked"])
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
        """Test that settings shows all configuration sections.

        This test ensures all major settings.yaml sections are displayed
        in the settings command output. If you add a new section to the
        defaults, add a check here.
        """
        storage, tmpdir = temp_storage
        with patch("serendipity.cli.StorageManager") as mock_cls:
            mock_cls.return_value = storage
            result = runner.invoke(app, ["settings"])
            assert result.exit_code == 0
            # Top-level settings
            assert "model" in result.stdout
            assert "total_count" in result.stdout
            assert "feedback_server_port" in result.stdout
            assert "thinking_tokens" in result.stdout
            # Sections - all major sections must be displayed
            assert "Approaches" in result.stdout
            assert "Media Types" in result.stdout
            assert "Pairings" in result.stdout
            assert "Context Sources" in result.stdout
            assert "Prompts" in result.stdout
            assert "Stylesheet" in result.stdout
            # Default approach types
            assert "convergent" in result.stdout
            assert "divergent" in result.stdout
            # Default media types (including new art/architecture)
            assert "article" in result.stdout
            assert "youtube" in result.stdout
            assert "book" in result.stdout
            assert "podcast" in result.stdout
            assert "music" in result.stdout
            assert "art" in result.stdout
            assert "architecture" in result.stdout
            # Default pairings
            assert "music" in result.stdout  # pairing
            assert "food" in result.stdout
            assert "exercise" in result.stdout
            assert "tip" in result.stdout
            assert "quote" in result.stdout
            assert "action" in result.stdout

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
    """Tests for the taste command (via profile manage taste)."""

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
            result = runner.invoke(app, ["profile", "manage", "taste"])
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
                result = runner.invoke(app, ["profile", "manage", "taste"])
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
        """Test that no args without profile shows onboarding tip."""
        from serendipity.agent import DiscoveryResult

        storage, tmpdir = temp_storage

        # Create output directory and mock HTML file
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "test.html").write_text("<html></html>")

        mock_result = DiscoveryResult(
            convergent=[],
            divergent=[],
            session_id="test-session",
            cost_usd=0.0,
            html_path=output_dir / "test.html",
        )

        with patch("serendipity.cli.StorageManager") as mock_cls, \
             patch("serendipity.cli.SerendipityAgent") as mock_agent_cls, \
             patch("serendipity.cli.ContextSourceManager") as mock_ctx_cls:
            mock_cls.return_value = storage

            # Mock agent
            mock_agent = MagicMock()
            mock_agent.run_sync.return_value = mock_result
            mock_agent.output_dir = output_dir
            mock_agent.render_json.return_value = '{"convergent": [], "divergent": []}'
            mock_agent_cls.return_value = mock_agent

            # Mock context manager
            mock_ctx = MagicMock()
            mock_ctx.get_enabled_source_names.return_value = []
            mock_ctx.get_mcp_servers.return_value = {}
            async def mock_init(*args, **kwargs):
                return []
            async def mock_build(*args, **kwargs):
                return ("", [])
            mock_ctx.initialize = mock_init
            mock_ctx.build_context = mock_build
            mock_ctx_cls.return_value = mock_ctx

            result = runner.invoke(app, ["-o", "json", "--dest", "stdout"])
            assert result.exit_code == 0
            # Should show tip about taste profile
            assert "taste" in result.stdout.lower()

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
        """Test that discover with no input and no profile shows onboarding tip."""
        from serendipity.agent import DiscoveryResult

        storage, tmpdir = temp_storage

        # Create output directory and mock HTML file
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "test.html").write_text("<html></html>")

        mock_result = DiscoveryResult(
            convergent=[],
            divergent=[],
            session_id="test-session",
            cost_usd=0.0,
            html_path=output_dir / "test.html",
        )

        with patch("serendipity.cli.StorageManager") as mock_cls, \
             patch("serendipity.cli.SerendipityAgent") as mock_agent_cls, \
             patch("serendipity.cli.ContextSourceManager") as mock_ctx_cls:
            mock_cls.return_value = storage

            # Mock agent
            mock_agent = MagicMock()
            mock_agent.run_sync.return_value = mock_result
            mock_agent.output_dir = output_dir
            mock_agent.render_json.return_value = '{"convergent": [], "divergent": []}'
            mock_agent_cls.return_value = mock_agent

            # Mock context manager
            mock_ctx = MagicMock()
            mock_ctx.get_enabled_source_names.return_value = []
            mock_ctx.get_mcp_servers.return_value = {}
            async def mock_init(*args, **kwargs):
                return []
            async def mock_build(*args, **kwargs):
                return ("", [])
            mock_ctx.initialize = mock_init
            mock_ctx.build_context = mock_build
            mock_ctx_cls.return_value = mock_ctx

            result = runner.invoke(app, ["discover", "-o", "json", "--dest", "stdout"])
            assert result.exit_code == 0
            # Should show tip about taste profile
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

    def test_discover_count_flag_overrides_settings(self, temp_storage_with_profile):
        """Test that --count flag overrides settings.total_count."""
        from serendipity.agent import DiscoveryResult
        from serendipity.models import Recommendation

        storage, tmpdir = temp_storage_with_profile

        # Create context file
        context_file = tmpdir / "context.txt"
        context_file.write_text("test context")

        # Create output directory and HTML file
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "test.html").write_text("<html></html>")

        mock_result = DiscoveryResult(
            convergent=[Recommendation(url="https://example.com", reason="test", approach="convergent")],
            divergent=[],
            session_id="test-session",
            cost_usd=0.01,
            html_path=output_dir / "test.html",
        )

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

            # Invoke with --count 3 (use browser destination to avoid stdout.write mocking issues)
            result = runner.invoke(app, ["discover", "--count", "3", str(context_file)])

            # Verify agent was created with types_config that has total_count=3
            assert mock_agent_cls.called
            agent_call_kwargs = mock_agent_cls.call_args.kwargs
            assert agent_call_kwargs["types_config"].total_count == 3

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

            # Check profile help - now shows generic manage/edit commands
            result = runner.invoke(app, ["profile", "--help"])
            assert result.exit_code == 0
            assert "manage" in result.stdout
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


class TestProfileManagementCommands:
    """Tests for profile management commands (list, create, use, delete, rename, export, import)."""

    @pytest.fixture
    def temp_root(self):
        """Create a temporary root directory for ProfileManager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            yield root

    def test_profile_list(self, temp_root):
        """Test listing profiles."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        pm.create_profile("work")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "list"])
            assert result.exit_code == 0
            assert "default" in result.stdout
            assert "work" in result.stdout
            assert "*" in result.stdout  # Active marker

    def test_profile_list_shows_env_var(self, temp_root):
        """Test that env var override is shown."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")

        with patch("serendipity.cli.ProfileManager") as mock_cls, \
             patch.dict("os.environ", {"SERENDIPITY_PROFILE": "work"}):
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "list"])
            assert result.exit_code == 0
            assert "SERENDIPITY_PROFILE" in result.stdout

    def test_profile_create(self, temp_root):
        """Test creating a new profile."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "create", "work"])
            assert result.exit_code == 0
            assert "Created profile" in result.stdout
            assert "work" in result.stdout

        # Verify profile was created
        assert pm.profile_exists("work")

    def test_profile_create_from_existing(self, temp_root):
        """Test creating a profile from an existing one."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        # Add some content to default
        (pm.get_profile_path("default") / "taste.md").write_text("# My Taste")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "create", "work", "--from", "default"])
            assert result.exit_code == 0
            assert "copied from" in result.stdout

        # Verify content was copied
        assert (pm.get_profile_path("work") / "taste.md").read_text() == "# My Taste"

    def test_profile_create_duplicate_fails(self, temp_root):
        """Test that creating a duplicate profile fails."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("work")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "create", "work"])
            assert result.exit_code == 1
            assert "already exists" in result.stdout

    def test_profile_use(self, temp_root):
        """Test switching to a different profile."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        pm.create_profile("work")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "use", "work"])
            assert result.exit_code == 0
            assert "Switched to profile" in result.stdout
            assert "work" in result.stdout

        # Verify active profile changed
        assert pm.get_active_profile() == "work"

    def test_profile_use_nonexistent_fails(self, temp_root):
        """Test that switching to a nonexistent profile fails."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "use", "nonexistent"])
            assert result.exit_code == 1
            assert "does not exist" in result.stdout

    def test_profile_delete_with_confirmation(self, temp_root):
        """Test deleting a profile with confirmation."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        pm.create_profile("work")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "delete", "work"], input="y\n")
            assert result.exit_code == 0
            assert "Deleted profile" in result.stdout

        assert not pm.profile_exists("work")

    def test_profile_delete_cancelled(self, temp_root):
        """Test cancelling profile deletion."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        pm.create_profile("work")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "delete", "work"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.stdout

        # Profile should still exist
        assert pm.profile_exists("work")

    def test_profile_delete_force(self, temp_root):
        """Test force deleting a profile without confirmation."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        pm.create_profile("work")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "delete", "work", "--force"])
            assert result.exit_code == 0
            assert "Deleted profile" in result.stdout

        assert not pm.profile_exists("work")

    def test_profile_delete_active_fails(self, temp_root):
        """Test that deleting the active profile fails."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        pm.set_active_profile("default")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "delete", "default", "--force"])
            assert result.exit_code == 1
            assert "active profile" in result.stdout.lower()

    def test_profile_delete_nonexistent_fails(self, temp_root):
        """Test that deleting a nonexistent profile fails."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "delete", "nonexistent", "--force"])
            assert result.exit_code == 1
            assert "does not exist" in result.stdout

    def test_profile_rename(self, temp_root):
        """Test renaming a profile."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        pm.create_profile("work")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "rename", "work", "business"])
            assert result.exit_code == 0
            assert "Renamed" in result.stdout
            assert "work" in result.stdout
            assert "business" in result.stdout

        assert not pm.profile_exists("work")
        assert pm.profile_exists("business")

    def test_profile_rename_nonexistent_fails(self, temp_root):
        """Test that renaming a nonexistent profile fails."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "rename", "nonexistent", "new"])
            assert result.exit_code == 1
            assert "does not exist" in result.stdout

    def test_profile_rename_to_existing_fails(self, temp_root):
        """Test that renaming to an existing profile name fails."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        pm.create_profile("work")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "rename", "work", "default"])
            assert result.exit_code == 1
            assert "already exists" in result.stdout

    def test_profile_export(self, temp_root):
        """Test exporting a profile."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        (pm.get_profile_path("default") / "taste.md").write_text("# My Taste")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "export", "default"])
            assert result.exit_code == 0
            assert "Exported" in result.stdout

        # Check archive was created
        archive_path = Path.cwd() / "default.tar.gz"
        assert archive_path.exists()
        archive_path.unlink()  # Cleanup

    def test_profile_export_active_default(self, temp_root):
        """Test that export defaults to active profile."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("myprofile")
        pm.set_active_profile("myprofile")
        (pm.get_profile_path("myprofile") / "taste.md").write_text("# My Taste")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "export"])
            assert result.exit_code == 0
            assert "myprofile" in result.stdout

        # Cleanup
        archive_path = Path.cwd() / "myprofile.tar.gz"
        if archive_path.exists():
            archive_path.unlink()

    def test_profile_export_custom_output(self, temp_root):
        """Test exporting to a custom output path."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        (pm.get_profile_path("default") / "taste.md").write_text("# My Taste")

        output_path = temp_root / "backup.tar.gz"

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "export", "default", "-o", str(output_path)])
            assert result.exit_code == 0
            assert "Exported" in result.stdout

        assert output_path.exists()

    def test_profile_import(self, temp_root):
        """Test importing a profile."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        pm.create_profile("other")
        (pm.get_profile_path("default") / "taste.md").write_text("# My Taste")

        # Export first
        archive_path = pm.export_profile("default")

        # Delete the profile (switch to other first)
        pm.set_active_profile("other")
        pm.delete_profile("default")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "import", str(archive_path)])
            assert result.exit_code == 0
            assert "Imported" in result.stdout

        assert pm.profile_exists("default")
        archive_path.unlink()  # Cleanup

    def test_profile_import_with_new_name(self, temp_root):
        """Test importing a profile with a new name."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")
        (pm.get_profile_path("default") / "taste.md").write_text("# My Taste")

        # Export first
        archive_path = pm.export_profile("default")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "import", str(archive_path), "--as", "imported"])
            assert result.exit_code == 0
            assert "imported" in result.stdout

        assert pm.profile_exists("imported")
        archive_path.unlink()  # Cleanup

    def test_profile_import_nonexistent_fails(self, temp_root):
        """Test that importing a nonexistent archive fails."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)
        pm.create_profile("default")

        with patch("serendipity.cli.ProfileManager") as mock_cls:
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "import", "/nonexistent/path.tar.gz"])
            assert result.exit_code == 1

    def test_profile_create_help_shows_interactive(self, temp_root):
        """Test that --help shows the interactive flag."""
        result = runner.invoke(app, ["profile", "create", "--help"])
        assert result.exit_code == 0
        assert "--interactive" in result.stdout
        assert "-i" in result.stdout
        assert "wizard" in result.stdout.lower()

    def test_profile_create_interactive(self, temp_root):
        """Test creating a profile with interactive flag."""
        from serendipity.storage import ProfileManager

        pm = ProfileManager(root_dir=temp_root)

        with patch("serendipity.cli.ProfileManager") as mock_cls, \
             patch("serendipity.cli._profile_interactive_wizard") as mock_wizard, \
             patch("serendipity.cli.StorageManager"):
            mock_cls.return_value = pm
            result = runner.invoke(app, ["profile", "create", "work", "-i"])
            assert result.exit_code == 0
            assert "Created profile" in result.stdout
            assert "Switched to profile" in result.stdout
            # Verify wizard was called
            mock_wizard.assert_called_once()

        # Verify profile was created and is now active
        assert pm.profile_exists("work")
        assert pm.get_active_profile() == "work"


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


