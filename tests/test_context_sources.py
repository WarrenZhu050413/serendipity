"""Tests for serendipity context sources module."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from serendipity.context_sources import (
    CommandSource,
    ContextResult,
    ContextSourceManager,
    LoaderSource,
    MCPConfig,
    MCPServerSource,
)
from serendipity.context_sources.builtins import (
    file_loader,
    history_loader,
)


class TestContextResult:
    """Tests for ContextResult dataclass."""

    def test_create_result(self):
        """Test creating a basic context result."""
        result = ContextResult(
            content="test content",
            prompt_section="<test>{content}</test>",
            warnings=["warning1"],
        )
        assert result.content == "test content"
        assert result.prompt_section == "<test>{content}</test>"
        assert result.warnings == ["warning1"]

    def test_empty_warnings_default(self):
        """Test that warnings defaults to empty list."""
        result = ContextResult(content="", prompt_section="")
        assert result.warnings == []


class TestMCPConfig:
    """Tests for MCPConfig dataclass."""

    def test_create_config(self):
        """Test creating MCP config."""
        config = MCPConfig(
            name="whorl",
            url="http://localhost:8081/mcp/",
            type="http",
            headers={"X-Password": "whorl"},
        )
        assert config.name == "whorl"
        assert config.url == "http://localhost:8081/mcp/"
        assert config.type == "http"
        assert config.headers == {"X-Password": "whorl"}

    def test_headers_default(self):
        """Test that headers defaults to empty dict."""
        config = MCPConfig(name="test", url="http://localhost", type="http")
        assert config.headers == {}


class TestLoaderSource:
    """Tests for LoaderSource class."""

    def test_init(self):
        """Test LoaderSource initialization."""
        config = {
            "enabled": True,
            "loader": "serendipity.context_sources.builtins.file_loader",
            "prompt_hint": "<test>\n{content}\n</test>",
            "options": {"path": "~/.test.md"},
        }
        source = LoaderSource("test", config)
        assert source.name == "test"
        assert source.enabled is True
        assert source.loader_path == "serendipity.context_sources.builtins.file_loader"
        assert source.options == {"path": "~/.test.md"}

    def test_disabled_by_default(self):
        """Test LoaderSource with enabled=False."""
        config = {"enabled": False, "loader": "some.module.func"}
        source = LoaderSource("test", config)
        assert source.enabled is False

    @pytest.mark.asyncio
    async def test_check_ready_valid_loader(self):
        """Test check_ready with valid loader path."""
        config = {
            "loader": "serendipity.context_sources.builtins.file_loader",
        }
        source = LoaderSource("test", config)
        console = MagicMock()
        ready, error = await source.check_ready(console)
        assert ready is True
        assert error == ""

    @pytest.mark.asyncio
    async def test_check_ready_invalid_loader(self):
        """Test check_ready with invalid loader path."""
        config = {
            "loader": "nonexistent.module.func",
        }
        source = LoaderSource("test", config)
        console = MagicMock()
        ready, error = await source.check_ready(console)
        assert ready is False
        assert "nonexistent.module.func" in error

    @pytest.mark.asyncio
    async def test_load_with_file_loader(self):
        """Test loading content with file_loader."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("Test content here")
            temp_path = f.name

        try:
            config = {
                "loader": "serendipity.context_sources.builtins.file_loader",
                "prompt_hint": "<taste>\n{content}\n</taste>",
                "options": {"path": temp_path},
            }
            source = LoaderSource("taste", config)

            # Mock storage (not needed for file_loader but required by interface)
            storage = MagicMock()

            result = await source.load(storage)
            assert result.content == "Test content here"
            assert "<taste>" in result.prompt_section
            assert "Test content here" in result.prompt_section
            assert result.warnings == []
        finally:
            Path(temp_path).unlink()

    def test_format_prompt_section(self):
        """Test format_prompt_section method."""
        config = {"prompt_hint": "<tag>\n{content}\n</tag>"}
        source = LoaderSource("test", config)
        result = source.format_prompt_section("hello world")
        assert result == "<tag>\nhello world\n</tag>"

    def test_format_prompt_section_empty(self):
        """Test format_prompt_section with empty content."""
        config = {"prompt_hint": "<tag>\n{content}\n</tag>"}
        source = LoaderSource("test", config)
        result = source.format_prompt_section("")
        assert result == ""


class TestBuiltinLoaders:
    """Tests for builtin loader functions."""

    def test_file_loader_exists(self):
        """Test file_loader with existing file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("Test content")
            temp_path = f.name

        try:
            storage = MagicMock()
            content, warnings = file_loader(storage, {"path": temp_path})
            assert content == "Test content"
            assert warnings == []
        finally:
            Path(temp_path).unlink()

    def test_file_loader_missing(self):
        """Test file_loader with missing file."""
        storage = MagicMock()
        content, warnings = file_loader(storage, {"path": "/nonexistent/path.md"})
        assert content == ""
        assert warnings == []  # Missing file is OK

    def test_file_loader_no_path(self):
        """Test file_loader without path option."""
        storage = MagicMock()
        content, warnings = file_loader(storage, {})
        assert content == ""
        assert len(warnings) == 1
        assert "No path" in warnings[0]

    def test_file_loader_word_count_warning(self):
        """Test file_loader word count warning."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            # Write content with 100 words
            f.write(" ".join(["word"] * 100))
            temp_path = f.name

        try:
            storage = MagicMock()
            content, warnings = file_loader(
                storage, {"path": temp_path, "warn_threshold": 50}
            )
            assert len(warnings) == 1
            assert "100" in warnings[0]
            assert ">50" in warnings[0]
        finally:
            Path(temp_path).unlink()

    def test_history_loader_empty(self):
        """Test history_loader with no history."""
        storage = MagicMock()
        storage.load_learnings.return_value = ""
        storage.load_recent_history.return_value = []
        storage.get_unextracted_entries.return_value = []

        content, warnings = history_loader(storage, {})
        assert content == ""
        assert warnings == []

    def test_history_loader_disabled(self):
        """Test history_loader returns empty when no data."""
        storage = MagicMock()
        storage.load_learnings.return_value = ""
        storage.load_recent_history.return_value = []
        storage.get_unextracted_entries.return_value = []

        content, warnings = history_loader(storage, {})
        assert content == ""
        assert warnings == []

    def test_history_loader_with_learnings(self):
        """Test history_loader with learnings."""
        storage = MagicMock()
        storage.load_learnings.return_value = "## Likes\n### Test\nI like this"
        storage.load_recent_history.return_value = []
        storage.get_unextracted_entries.return_value = []

        content, warnings = history_loader(storage, {})
        assert "<discovery_learnings>" in content
        assert "I like this" in content

    def test_history_loader_with_recent_entries(self):
        """Test history_loader includes recent entries."""
        from serendipity.storage import HistoryEntry

        storage = MagicMock()
        storage.load_learnings.return_value = ""
        storage.load_recent_history.return_value = [
            HistoryEntry(
                url="https://recent1.com",
                reason="test",
                type="convergent",
                feedback="liked",
                timestamp="2024-01-15T10:30:00Z",
                session_id="abc123",
            ),
            HistoryEntry(
                url="https://recent2.com",
                reason="test",
                type="divergent",
                feedback=None,
                timestamp="2024-01-15T10:31:00Z",
                session_id="abc123",
            ),
        ]
        storage.get_unextracted_entries.return_value = []

        content, warnings = history_loader(storage, {})
        assert "Recently shown" in content
        assert "https://recent1.com" in content
        assert "convergent, liked" in content
        assert "https://recent2.com" in content
        assert "divergent, no feedback" in content

    def test_history_loader_with_unextracted_liked(self):
        """Test history_loader includes unextracted liked entries."""
        from serendipity.storage import HistoryEntry

        storage = MagicMock()
        storage.load_learnings.return_value = ""
        storage.load_recent_history.return_value = []

        # Return liked entries for "liked" filter, empty for "disliked"
        def mock_get_unextracted(feedback_type=None):
            if feedback_type == "liked":
                return [
                    HistoryEntry(
                        url="https://liked.com",
                        reason="This is a great article about minimalism",
                        type="convergent",
                        feedback="liked",
                        timestamp="2024-01-15T10:30:00Z",
                        session_id="abc123",
                    ),
                ]
            return []

        storage.get_unextracted_entries.side_effect = mock_get_unextracted

        content, warnings = history_loader(storage, {})
        assert "Items you've liked" in content
        assert "https://liked.com" in content
        assert "great article" in content

    def test_history_loader_with_unextracted_disliked(self):
        """Test history_loader includes unextracted disliked entries."""
        from serendipity.storage import HistoryEntry

        storage = MagicMock()
        storage.load_learnings.return_value = ""
        storage.load_recent_history.return_value = []

        # Return disliked entries for "disliked" filter
        def mock_get_unextracted(feedback_type=None):
            if feedback_type == "disliked":
                return [
                    HistoryEntry(
                        url="https://disliked.com",
                        reason="Not my taste",
                        type="divergent",
                        feedback="disliked",
                        timestamp="2024-01-15T10:30:00Z",
                        session_id="abc123",
                    ),
                ]
            return []

        storage.get_unextracted_entries.side_effect = mock_get_unextracted

        content, warnings = history_loader(storage, {})
        assert "Items you didn't like" in content
        assert "https://disliked.com" in content

    def test_history_loader_word_count_warning(self):
        """Test history_loader word count warning."""
        storage = MagicMock()
        # Create learnings with many words
        storage.load_learnings.return_value = " ".join(["word"] * 200)
        storage.load_recent_history.return_value = []
        storage.get_unextracted_entries.return_value = []

        content, warnings = history_loader(storage, {"warn_threshold": 50})
        assert len(warnings) == 1
        assert ">50" in warnings[0]

    def test_history_loader_include_unextracted_false(self):
        """Test history_loader with include_unextracted=False."""
        from serendipity.storage import HistoryEntry

        storage = MagicMock()
        storage.load_learnings.return_value = "Some learnings"
        storage.load_recent_history.return_value = []

        content, warnings = history_loader(storage, {"include_unextracted": False})

        # Should not call get_unextracted_entries
        storage.get_unextracted_entries.assert_not_called()
        assert "learnings" in content.lower()


class TestMCPServerSource:
    """Tests for MCPServerSource class."""

    def test_init(self):
        """Test MCPServerSource initialization."""
        config = {
            "enabled": False,
            "server": {"url": "http://localhost:{port}/mcp/", "type": "http"},
            "port": {"default": 8081, "max_retries": 5},
            "tools": {"allowed": ["mcp__test__tool"]},
            "system_prompt_hint": "Use the test tool",
        }
        source = MCPServerSource("test", config)
        assert source.name == "test"
        assert source.enabled is False
        assert source._port is None

    @pytest.mark.asyncio
    async def test_check_ready_cli_not_installed(self):
        """Test check_ready when CLI is not installed."""
        config = {
            "setup": {
                "cli_command": "nonexistent_cli",
                "install_hint": "pip install nonexistent",
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        ready, error = await source.check_ready(console)
        assert ready is False
        assert "nonexistent_cli not installed" in error

    @pytest.mark.asyncio
    async def test_check_ready_home_dir_missing(self):
        """Test check_ready when home dir is missing."""
        config = {
            "setup": {
                "home_dir": "/nonexistent/dir",
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        ready, error = await source.check_ready(console)
        assert ready is False
        assert "/nonexistent/dir not found" in error

    @pytest.mark.asyncio
    async def test_check_ready_success(self):
        """Test check_ready with no setup requirements."""
        config = {}
        source = MCPServerSource("test", config)
        console = MagicMock()

        ready, error = await source.check_ready(console)
        assert ready is True
        assert error == ""

    @pytest.mark.asyncio
    async def test_load_returns_empty(self):
        """Test that MCP sources return empty content."""
        config = {}
        source = MCPServerSource("test", config)
        storage = MagicMock()

        result = await source.load(storage)
        assert result.content == ""
        assert result.prompt_section == ""

    def test_get_mcp_config_not_running(self):
        """Test get_mcp_config when server not running."""
        config = {}
        source = MCPServerSource("test", config)
        assert source.get_mcp_config() is None

    def test_get_mcp_config_running(self):
        """Test get_mcp_config when server is running."""
        config = {
            "server": {
                "url": "http://localhost:{port}/mcp/",
                "type": "http",
                "headers": {"X-Password": "test"},
            },
        }
        source = MCPServerSource("test", config)
        source._port = 8081

        mcp_config = source.get_mcp_config()
        assert mcp_config is not None
        assert mcp_config.name == "test"
        assert mcp_config.url == "http://localhost:8081/mcp/"
        assert mcp_config.headers == {"X-Password": "test"}

    def test_get_allowed_tools(self):
        """Test get_allowed_tools."""
        config = {
            "tools": {"allowed": ["tool1", "tool2"]},
        }
        source = MCPServerSource("test", config)
        assert source.get_allowed_tools() == ["tool1", "tool2"]

    def test_get_system_prompt_hint(self):
        """Test get_system_prompt_hint with legacy key."""
        config = {
            "system_prompt_hint": "Use this tool first",
        }
        source = MCPServerSource("test", config)
        assert source.get_system_prompt_hint() == "Use this tool first"

    def test_get_system_prompt_hint_with_prompt_hint(self):
        """Test get_system_prompt_hint with new prompt_hint key."""
        config = {
            "prompt_hint": "Use the new key",
        }
        source = MCPServerSource("test", config)
        assert source.get_system_prompt_hint() == "Use the new key"

    def test_prompt_hint_takes_precedence(self):
        """Test that prompt_hint takes precedence over system_prompt_hint."""
        config = {
            "prompt_hint": "New hint",
            "system_prompt_hint": "Old hint",
        }
        source = MCPServerSource("test", config)
        assert source.get_system_prompt_hint() == "New hint"


class TestContextSourceManager:
    """Tests for ContextSourceManager class."""

    def _make_config_with_sources(self, sources: dict):
        """Create a mock TypesConfig with context_sources."""
        config = MagicMock()
        config.context_sources = sources
        return config

    def test_init_loader_sources(self):
        """Test initializing with loader sources."""
        sources = {
            "taste": {
                "type": "loader",
                "enabled": True,
                "loader": "serendipity.context_sources.builtins.file_loader",
                "options": {"path": "~/.test.md"},
            },
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)
        assert "taste" in manager.sources
        assert isinstance(manager.sources["taste"], LoaderSource)

    def test_init_mcp_sources(self):
        """Test initializing with MCP sources."""
        sources = {
            "whorl": {
                "type": "mcp",
                "enabled": False,
                "server": {"url": "http://localhost:8081/mcp/"},
            },
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)
        assert "whorl" in manager.sources
        assert isinstance(manager.sources["whorl"], MCPServerSource)

    @pytest.mark.asyncio
    async def test_initialize_enable_sources(self):
        """Test initialize with enable_sources override."""
        sources = {
            "taste": {
                "type": "loader",
                "enabled": False,
                "loader": "serendipity.context_sources.builtins.file_loader",
                "options": {"path": "/nonexistent"},
            },
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)
        assert manager.sources["taste"].enabled is False

        await manager.initialize(enable_sources=["taste"])
        assert manager.sources["taste"].enabled is True

    @pytest.mark.asyncio
    async def test_initialize_disable_sources(self):
        """Test initialize with disable_sources override."""
        sources = {
            "taste": {
                "type": "loader",
                "enabled": True,
                "loader": "serendipity.context_sources.builtins.file_loader",
                "options": {"path": "/nonexistent"},
            },
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)
        await manager.initialize(disable_sources=["taste"])
        assert manager.sources["taste"].enabled is False

    @pytest.mark.asyncio
    async def test_build_context(self):
        """Test build_context combines sources."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("taste content")
            taste_path = f.name

        try:
            sources = {
                "taste": {
                    "type": "loader",
                    "enabled": True,
                    "loader": "serendipity.context_sources.builtins.file_loader",
                    "prompt_hint": "<taste>\n{content}\n</taste>",
                    "options": {"path": taste_path},
                },
            }
            config = self._make_config_with_sources(sources)
            console = MagicMock()
            storage = MagicMock()

            manager = ContextSourceManager(config, console)
            await manager.initialize()

            context, warnings = await manager.build_context(storage)
            assert "<taste>" in context
            assert "taste content" in context
        finally:
            Path(taste_path).unlink()

    def test_get_mcp_servers(self):
        """Test get_mcp_servers aggregates configs."""
        sources = {
            "whorl": {
                "type": "mcp",
                "enabled": True,
                "server": {
                    "url": "http://localhost:{port}/mcp/",
                    "type": "http",
                },
            },
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)
        # Simulate server running
        manager.sources["whorl"]._port = 8081

        servers = manager.get_mcp_servers()
        assert "whorl" in servers
        assert servers["whorl"]["url"] == "http://localhost:8081/mcp/"

    def test_get_allowed_tools(self):
        """Test get_allowed_tools aggregates tools."""
        sources = {
            "whorl": {
                "type": "mcp",
                "enabled": True,
                "tools": {"allowed": ["tool1", "tool2"]},
            },
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)
        tools = manager.get_allowed_tools()
        assert "tool1" in tools
        assert "tool2" in tools

    def test_get_system_prompt_hints(self):
        """Test get_system_prompt_hints combines hints."""
        sources = {
            "whorl": {
                "type": "mcp",
                "enabled": True,
                "system_prompt_hint": "Use whorl first.",
            },
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)
        hints = manager.get_system_prompt_hints()
        assert "Use whorl first." in hints

    def test_get_enabled_source_names(self):
        """Test get_enabled_source_names."""
        sources = {
            "taste": {"type": "loader", "enabled": True, "loader": "mod.func"},
            "whorl": {"type": "mcp", "enabled": False},
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)
        enabled = manager.get_enabled_source_names()
        assert "taste" in enabled
        assert "whorl" not in enabled


class TestContextSourceManagerIntegration:
    """Integration tests for ContextSourceManager."""

    def _make_config_with_sources(self, sources: dict):
        """Create a mock TypesConfig with context_sources."""
        config = MagicMock()
        config.context_sources = sources
        return config

    @pytest.mark.asyncio
    async def test_multiple_sources_combined(self):
        """Test combining context from multiple sources."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f1:
            f1.write("Taste content here")
            taste_path = f1.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f2:
            f2.write("Extra content here")
            extra_path = f2.name

        try:
            sources = {
                "taste": {
                    "type": "loader",
                    "enabled": True,
                    "loader": "serendipity.context_sources.builtins.file_loader",
                    "prompt_hint": "<taste>\n{content}\n</taste>",
                    "options": {"path": taste_path},
                },
                "extra": {
                    "type": "loader",
                    "enabled": True,
                    "loader": "serendipity.context_sources.builtins.file_loader",
                    "prompt_hint": "<extra>\n{content}\n</extra>",
                    "options": {"path": extra_path},
                },
            }
            config = self._make_config_with_sources(sources)
            console = MagicMock()
            storage = MagicMock()

            manager = ContextSourceManager(config, console)
            await manager.initialize()

            context, warnings = await manager.build_context(storage)

            assert "<taste>" in context
            assert "Taste content here" in context
            assert "<extra>" in context
            assert "Extra content here" in context
        finally:
            Path(taste_path).unlink()
            Path(extra_path).unlink()

    @pytest.mark.asyncio
    async def test_failed_source_disabled(self):
        """Test that sources failing check_ready are disabled."""
        sources = {
            "broken": {
                "type": "loader",
                "enabled": True,
                "loader": "nonexistent.module.func",
            },
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)
        warnings = await manager.initialize()

        assert len(warnings) >= 1
        assert manager.sources["broken"].enabled is False

    @pytest.mark.asyncio
    async def test_warnings_aggregated(self):
        """Test that warnings from all sources are aggregated."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            # Write lots of words to trigger warning
            f.write(" ".join(["word"] * 200))
            warn_path = f.name

        try:
            sources = {
                "warn_source": {
                    "type": "loader",
                    "enabled": True,
                    "loader": "serendipity.context_sources.builtins.file_loader",
                    "prompt_hint": "<test>\n{content}\n</test>",
                    "options": {"path": warn_path, "warn_threshold": 50},
                },
            }
            config = self._make_config_with_sources(sources)
            console = MagicMock()
            storage = MagicMock()

            manager = ContextSourceManager(config, console)
            await manager.initialize()

            context, warnings = await manager.build_context(storage)

            assert len(warnings) >= 1
            assert ">50" in warnings[0]
        finally:
            Path(warn_path).unlink()

    @pytest.mark.asyncio
    async def test_runtime_enable_disable(self):
        """Test runtime enable/disable of sources."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("Test content")
            test_path = f.name

        try:
            sources = {
                "source1": {
                    "type": "loader",
                    "enabled": True,
                    "loader": "serendipity.context_sources.builtins.file_loader",
                    "prompt_hint": "<s1>\n{content}\n</s1>",
                    "options": {"path": test_path},
                },
                "source2": {
                    "type": "loader",
                    "enabled": False,
                    "loader": "serendipity.context_sources.builtins.file_loader",
                    "prompt_hint": "<s2>\n{content}\n</s2>",
                    "options": {"path": test_path},
                },
            }
            config = self._make_config_with_sources(sources)
            console = MagicMock()
            storage = MagicMock()

            manager = ContextSourceManager(config, console)

            # Initially, source1 enabled, source2 disabled
            await manager.initialize()
            assert manager.sources["source1"].enabled is True
            assert manager.sources["source2"].enabled is False

            # Enable source2, disable source1
            await manager.initialize(
                enable_sources=["source2"],
                disable_sources=["source1"]
            )
            assert manager.sources["source1"].enabled is False
            assert manager.sources["source2"].enabled is True

            # Build context should only include source2
            context, _ = await manager.build_context(storage)
            assert "<s2>" in context
            assert "<s1>" not in context
        finally:
            Path(test_path).unlink()

    def test_unknown_source_type_logged(self):
        """Test that unknown source types are logged."""
        sources = {
            "weird": {
                "type": "unknown_type",
                "enabled": True,
            },
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)

        # Should not be in sources
        assert "weird" not in manager.sources
        # Should print warning
        console.print.assert_called()


class TestMCPServerSourceLifecycle:
    """Tests for MCPServerSource lifecycle management."""

    @pytest.mark.asyncio
    async def test_port_detection_running_server(self):
        """Test detecting an already running server."""
        config = {
            "enabled": True,
            "server": {
                "url": "http://localhost:{port}/mcp/",
                "type": "http",
            },
            "health_check": {
                "endpoint": "/health",
                "timeout": 1.0,
            },
            "port": {
                "default": 8081,
                "max_retries": 3,
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        # Mock httpx to simulate server running
        with patch("serendipity.context_sources.mcp.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_httpx.get.return_value = mock_response
            mock_httpx.RequestError = Exception

            result = await source.ensure_running(console)

            assert result is True
            assert source._port == 8081

    @pytest.mark.asyncio
    async def test_auto_start_disabled(self):
        """Test that auto_start disabled returns False when no server."""
        config = {
            "enabled": True,
            "health_check": {
                "endpoint": "/health",
                "timeout": 0.1,
            },
            "port": {
                "default": 9999,
                "max_retries": 1,
            },
            "auto_start": {
                "enabled": False,
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        with patch("serendipity.context_sources.mcp.httpx") as mock_httpx:
            mock_httpx.RequestError = Exception
            mock_httpx.get.side_effect = Exception("Connection refused")

            result = await source.ensure_running(console)

            assert result is False
            # Should print warning about auto_start disabled
            console.print.assert_called()

    @pytest.mark.asyncio
    async def test_check_ready_validates_setup(self):
        """Test that check_ready validates all setup requirements."""
        config = {
            "setup": {
                "cli_command": "nonexistent_command_xyz",
                "install_hint": "pip install xyz",
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        ready, error = await source.check_ready(console)

        assert ready is False
        assert "not installed" in error

    @pytest.mark.asyncio
    async def test_check_ready_validates_home_dir(self):
        """Test that check_ready validates home directory."""
        config = {
            "setup": {
                "home_dir": "/nonexistent/path/xyz123",
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        ready, error = await source.check_ready(console)

        assert ready is False
        assert "not found" in error

    @pytest.mark.asyncio
    async def test_check_ready_validates_docs_dir(self):
        """Test that check_ready validates docs directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "setup": {
                    "docs_dir": tmpdir,  # Empty directory
                },
            }
            source = MCPServerSource("test", config)
            console = MagicMock()

            ready, error = await source.check_ready(console)

            assert ready is False
            assert "No documents" in error

    def test_get_mcp_config_with_port_substitution(self):
        """Test URL port substitution in get_mcp_config."""
        config = {
            "server": {
                "url": "http://localhost:{port}/api/mcp/",
                "type": "http",
                "headers": {"X-Key": "secret"},
            },
        }
        source = MCPServerSource("test", config)
        source._port = 9999

        mcp_config = source.get_mcp_config()

        assert mcp_config is not None
        assert "9999" in mcp_config.url
        assert mcp_config.headers == {"X-Key": "secret"}


class TestIsPortAvailable:
    """Tests for _is_port_available helper function."""

    def test_port_available(self):
        """Test detecting available port."""
        from serendipity.context_sources.mcp import _is_port_available

        # Use a high port that's unlikely to be in use
        result = _is_port_available(59999)
        # Result depends on system state, but should not raise
        assert isinstance(result, bool)

    def test_port_in_use(self):
        """Test detecting port in use."""
        import socket

        from serendipity.context_sources.mcp import _is_port_available

        # Bind a socket to make port unavailable
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("localhost", 59998))
            sock.listen(1)

            result = _is_port_available(59998)
            assert result is False
        finally:
            sock.close()


class TestMCPAutoStart:
    """Tests for MCPServerSource auto-start functionality."""

    @pytest.mark.asyncio
    async def test_auto_start_no_available_port(self):
        """Test auto-start when no ports available."""
        config = {
            "enabled": True,
            "health_check": {
                "endpoint": "/health",
                "timeout": 0.1,
            },
            "port": {
                "default": 8081,
                "max_retries": 2,
            },
            "auto_start": {
                "enabled": True,
                "command": ["echo", "test"],
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        # Mock everything to fail
        with patch("serendipity.context_sources.mcp.httpx") as mock_httpx:
            mock_httpx.RequestError = Exception
            mock_httpx.get.side_effect = Exception("Connection refused")

            with patch("serendipity.context_sources.mcp._is_port_available") as mock_port:
                # All ports unavailable
                mock_port.return_value = False

                result = await source.ensure_running(console)

                assert result is False

    @pytest.mark.asyncio
    async def test_auto_start_no_command(self):
        """Test auto-start when no command configured."""
        config = {
            "enabled": True,
            "health_check": {
                "endpoint": "/health",
                "timeout": 0.1,
            },
            "port": {
                "default": 8081,
                "max_retries": 2,
            },
            "auto_start": {
                "enabled": True,
                "command": [],  # Empty command
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        with patch("serendipity.context_sources.mcp.httpx") as mock_httpx:
            mock_httpx.RequestError = Exception
            mock_httpx.get.side_effect = Exception("Connection refused")

            with patch("serendipity.context_sources.mcp._is_port_available") as mock_port:
                mock_port.return_value = True

                result = await source.ensure_running(console)

                assert result is False

    @pytest.mark.asyncio
    async def test_auto_start_command_not_found(self):
        """Test auto-start when command not found."""
        config = {
            "enabled": True,
            "health_check": {
                "endpoint": "/health",
                "timeout": 0.1,
            },
            "port": {
                "default": 8081,
                "max_retries": 2,
            },
            "auto_start": {
                "enabled": True,
                "command": ["nonexistent_command_xyz"],
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        with patch("serendipity.context_sources.mcp.httpx") as mock_httpx:
            mock_httpx.RequestError = Exception
            mock_httpx.get.side_effect = Exception("Connection refused")

            with patch("serendipity.context_sources.mcp._is_port_available") as mock_port:
                mock_port.return_value = True

                result = await source.ensure_running(console)

                assert result is False

    @pytest.mark.asyncio
    async def test_auto_start_server_fails_health_check(self):
        """Test auto-start when server starts but fails health check."""
        config = {
            "enabled": True,
            "health_check": {
                "endpoint": "/health",
                "timeout": 0.1,
            },
            "port": {
                "default": 8081,
                "max_retries": 2,
            },
            "auto_start": {
                "enabled": True,
                "command": ["sleep", "0.1"],  # Command that runs but doesn't serve
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        with patch("serendipity.context_sources.mcp.httpx") as mock_httpx:
            mock_httpx.RequestError = Exception
            mock_httpx.get.side_effect = Exception("Connection refused")

            with patch("serendipity.context_sources.mcp._is_port_available") as mock_port:
                mock_port.return_value = True

                with patch("serendipity.context_sources.mcp.time.sleep"):
                    result = await source.ensure_running(console)

                    # Should fail after retries
                    assert result is False

    @pytest.mark.asyncio
    async def test_port_detection_on_non_default_port(self):
        """Test detecting server on non-default port."""
        config = {
            "enabled": True,
            "server": {
                "url": "http://localhost:{port}/mcp/",
                "type": "http",
            },
            "health_check": {
                "endpoint": "/health",
                "timeout": 1.0,
            },
            "port": {
                "default": 8081,
                "max_retries": 3,
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        # Simulate server running on port 8082 (not default 8081)
        call_count = [0]

        def mock_get(url, timeout=None):
            call_count[0] += 1
            if "8082" in url:
                mock_response = MagicMock()
                mock_response.status_code = 200
                return mock_response
            raise Exception("Connection refused")

        with patch("serendipity.context_sources.mcp.httpx") as mock_httpx:
            mock_httpx.get.side_effect = mock_get
            mock_httpx.RequestError = Exception

            result = await source.ensure_running(console)

            assert result is True
            assert source._port == 8082
            # Should print message about non-default port
            console.print.assert_called()


class TestContextSourceManagerEdgeCases:
    """Edge case tests for ContextSourceManager."""

    def _make_config_with_sources(self, sources: dict):
        """Create a mock TypesConfig with context_sources."""
        config = MagicMock()
        config.context_sources = sources
        return config

    @pytest.mark.asyncio
    async def test_initialize_unknown_enable_source(self):
        """Test initialize with unknown source in enable_sources list."""
        sources = {
            "taste": {
                "type": "loader",
                "enabled": False,
                "loader": "serendipity.context_sources.builtins.file_loader",
                "options": {"path": "/nonexistent"},
            },
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)
        warnings = await manager.initialize(enable_sources=["unknown_source"])

        assert len(warnings) >= 1
        assert any("Unknown source" in w for w in warnings)

    @pytest.mark.asyncio
    async def test_initialize_mcp_ensure_running_fails(self):
        """Test initialize when MCP server ensure_running fails."""
        sources = {
            "test_mcp": {
                "type": "mcp",
                "enabled": True,
                "server": {"url": "http://localhost:{port}/mcp/"},
                "health_check": {"endpoint": "/health", "timeout": 0.1},
                "port": {"default": 9999, "max_retries": 1},
                "auto_start": {"enabled": False},
            },
        }
        config = self._make_config_with_sources(sources)
        console = MagicMock()

        manager = ContextSourceManager(config, console)

        # Mock httpx to fail health checks
        with patch("serendipity.context_sources.mcp.httpx") as mock_httpx:
            mock_httpx.RequestError = Exception
            mock_httpx.get.side_effect = Exception("Connection refused")

            warnings = await manager.initialize()

            # Should have warning about failed MCP server
            assert len(warnings) >= 1
            assert any("Failed to start MCP server" in w for w in warnings)
            # Source should be disabled
            assert manager.sources["test_mcp"].enabled is False

    def test_init_with_context_source_config_objects(self):
        """Test initialization with ContextSourceConfig objects (raw_config path)."""
        # Simulate ContextSourceConfig-like object with raw_config attribute
        source_config = MagicMock()
        source_config.raw_config = {
            "type": "loader",
            "loader": "serendipity.context_sources.builtins.file_loader",
            "options": {"path": "~/.test.md"},
        }
        source_config.enabled = True
        source_config.prompt_hint = "<test>{content}</test>"
        source_config.description = "Test source"

        config = MagicMock()
        config.context_sources = {"test": source_config}
        console = MagicMock()

        manager = ContextSourceManager(config, console)

        assert "test" in manager.sources
        assert isinstance(manager.sources["test"], LoaderSource)
        assert manager.sources["test"].enabled is True


class TestMCPAutoStartAdvanced:
    """Advanced tests for MCP auto-start with log files and exceptions."""

    @pytest.mark.asyncio
    async def test_auto_start_with_log_path(self, tmp_path):
        """Test auto-start with log file configuration."""
        log_file = tmp_path / "server.log"
        config = {
            "enabled": True,
            "health_check": {"endpoint": "/health", "timeout": 0.1},
            "port": {"default": 8081, "max_retries": 1},
            "auto_start": {
                "enabled": True,
                "command": ["echo", "starting"],
                "log_path": str(log_file),
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        # Mock httpx to fail (server won't actually start)
        with patch("serendipity.context_sources.mcp.httpx") as mock_httpx:
            mock_httpx.RequestError = Exception
            mock_httpx.get.side_effect = Exception("Connection refused")

            with patch("serendipity.context_sources.mcp._is_port_available") as mock_port:
                mock_port.return_value = True

                with patch("serendipity.context_sources.mcp.time.sleep"):
                    result = await source.ensure_running(console)

        # Even though server fails, log file parent should be created
        assert result is False

    @pytest.mark.asyncio
    async def test_auto_start_success_default_port(self):
        """Test auto-start success on default port shows correct message."""
        config = {
            "enabled": True,
            "health_check": {"endpoint": "/health", "timeout": 0.5},
            "port": {"default": 8081, "max_retries": 3},
            "auto_start": {
                "enabled": True,
                "command": ["echo", "starting"],
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        # Track calls to distinguish initial check vs post-start check
        check_phase = [0]  # 0 = initial checks, 1 = after start

        def mock_get(url, timeout=None):
            # During initial check (phase 0), fail all ports
            # During post-start check (phase 1), succeed
            if check_phase[0] == 0:
                raise Exception("Connection refused")
            mock_response = MagicMock()
            mock_response.status_code = 200
            return mock_response

        def mock_popen(*args, **kwargs):
            check_phase[0] = 1  # Switch to phase 1 after Popen
            return MagicMock()

        with patch("serendipity.context_sources.mcp.httpx") as mock_httpx:
            mock_httpx.RequestError = Exception
            mock_httpx.get.side_effect = mock_get

            with patch("serendipity.context_sources.mcp._is_port_available") as mock_port:
                mock_port.return_value = True

                with patch("serendipity.context_sources.mcp.subprocess.Popen", side_effect=mock_popen):
                    with patch("serendipity.context_sources.mcp.time.sleep"):
                        result = await source.ensure_running(console)

        assert result is True
        assert source._port == 8081
        # Should have printed success message
        console.print.assert_called()

    @pytest.mark.asyncio
    async def test_auto_start_generic_exception(self):
        """Test auto-start handles generic exceptions."""
        config = {
            "enabled": True,
            "health_check": {"endpoint": "/health", "timeout": 0.1},
            "port": {"default": 8081, "max_retries": 1},
            "auto_start": {
                "enabled": True,
                "command": ["echo", "test"],
            },
        }
        source = MCPServerSource("test", config)
        console = MagicMock()

        with patch("serendipity.context_sources.mcp.httpx") as mock_httpx:
            mock_httpx.RequestError = Exception
            mock_httpx.get.side_effect = Exception("Connection refused")

            with patch("serendipity.context_sources.mcp._is_port_available") as mock_port:
                mock_port.return_value = True

                with patch("serendipity.context_sources.mcp.subprocess.Popen") as mock_popen:
                    # Popen raises a generic exception
                    mock_popen.side_effect = RuntimeError("Unexpected error")

                    result = await source.ensure_running(console)

        assert result is False
        # Should print error message
        assert any("Failed to start" in str(call) for call in console.print.call_args_list)


class TestLoaderSourceEdgeCases:
    """Edge case tests for LoaderSource."""

    @pytest.mark.asyncio
    async def test_loader_exception_returns_warning(self):
        """Test that loader exceptions are captured as warnings."""
        config = {
            "loader": "serendipity.context_sources.builtins.file_loader",
            "prompt_hint": "<test>\n{content}\n</test>",
            "options": {},  # Missing required 'path' option
        }
        source = LoaderSource("test", config)
        storage = MagicMock()

        result = await source.load(storage)

        assert result.content == ""
        assert len(result.warnings) >= 1

    @pytest.mark.asyncio
    async def test_loader_caches_function(self):
        """Test that loader function is cached after first import."""
        config = {
            "loader": "serendipity.context_sources.builtins.file_loader",
        }
        source = LoaderSource("test", config)

        # First call imports
        func1 = source._get_loader_func()
        # Second call should return cached
        func2 = source._get_loader_func()

        assert func1 is func2

    def test_format_prompt_section_with_newlines(self):
        """Test format_prompt_section preserves content formatting."""
        config = {
            "prompt_hint": "<section>\n{content}\n</section>",
        }
        source = LoaderSource("test", config)

        content = "Line 1\nLine 2\nLine 3"
        result = source.format_prompt_section(content)

        assert "Line 1\nLine 2\nLine 3" in result
        assert result.startswith("<section>")
        assert result.endswith("</section>")


class TestCommandSource:
    """Tests for CommandSource class."""

    def test_init(self):
        """Test CommandSource initialization."""
        config = {
            "enabled": True,
            "command": "echo hello",
            "timeout": 10,
            "prompt_hint": "<output>\n{content}\n</output>",
        }
        source = CommandSource("test", config)
        assert source.name == "test"
        assert source.enabled is True
        assert source.command == "echo hello"
        assert source.timeout == 10

    def test_init_defaults(self):
        """Test CommandSource default values."""
        config = {}
        source = CommandSource("test", config)
        assert source.command == ""
        assert source.timeout == 30

    @pytest.mark.asyncio
    async def test_check_ready_with_command(self):
        """Test check_ready passes when command is set."""
        config = {"command": "echo test"}
        source = CommandSource("test", config)
        console = MagicMock()

        ready, error = await source.check_ready(console)
        assert ready is True
        assert error == ""

    @pytest.mark.asyncio
    async def test_check_ready_no_command(self):
        """Test check_ready fails when command is empty."""
        config = {"command": ""}
        source = CommandSource("test", config)
        console = MagicMock()

        ready, error = await source.check_ready(console)
        assert ready is False
        assert "No command specified" in error

    @pytest.mark.asyncio
    async def test_load_simple_command(self):
        """Test loading output from a simple command."""
        config = {
            "command": "echo 'Hello, World!'",
            "prompt_hint": "<output>\n{content}\n</output>",
        }
        source = CommandSource("test", config)
        storage = MagicMock()

        result = await source.load(storage)

        assert "Hello, World!" in result.content
        assert "<output>" in result.prompt_section
        assert result.warnings == []

    @pytest.mark.asyncio
    async def test_load_multiline_command(self):
        """Test loading output from command with multiple lines."""
        config = {
            "command": "printf 'Line1\\nLine2\\nLine3'",
            "prompt_hint": "{content}",
        }
        source = CommandSource("test", config)
        storage = MagicMock()

        result = await source.load(storage)

        assert "Line1" in result.content
        assert "Line2" in result.content
        assert "Line3" in result.content

    @pytest.mark.asyncio
    async def test_load_command_with_pipe(self):
        """Test loading output from piped command."""
        config = {
            "command": "echo 'a b c d' | wc -w",
            "prompt_hint": "{content}",
        }
        source = CommandSource("test", config)
        storage = MagicMock()

        result = await source.load(storage)

        # wc -w should output 4 (four words)
        assert "4" in result.content

    @pytest.mark.asyncio
    async def test_load_no_command(self):
        """Test load returns empty when no command."""
        config = {"command": ""}
        source = CommandSource("test", config)
        storage = MagicMock()

        result = await source.load(storage)

        assert result.content == ""
        assert result.prompt_section == ""
        assert len(result.warnings) == 1
        assert "No command specified" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_load_command_stderr(self):
        """Test that stderr is captured as warning."""
        config = {
            "command": "echo 'stdout' && >&2 echo 'stderr'",
            "prompt_hint": "{content}",
        }
        source = CommandSource("test", config)
        storage = MagicMock()

        result = await source.load(storage)

        assert "stdout" in result.content
        assert len(result.warnings) >= 1
        assert "stderr" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_load_command_nonzero_exit(self):
        """Test that non-zero exit code is captured as warning."""
        config = {
            "command": "exit 1",
            "prompt_hint": "{content}",
        }
        source = CommandSource("test", config)
        storage = MagicMock()

        result = await source.load(storage)

        assert len(result.warnings) >= 1
        assert "exit" in result.warnings[0].lower() or "code 1" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_load_command_timeout(self):
        """Test that timeout is handled gracefully."""
        config = {
            "command": "sleep 10",
            "timeout": 0.1,  # Very short timeout
            "prompt_hint": "{content}",
        }
        source = CommandSource("test", config)
        storage = MagicMock()

        result = await source.load(storage)

        assert result.content == ""
        assert len(result.warnings) == 1
        assert "timed out" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_context_source_manager_recognizes_command(self):
        """Test that ContextSourceManager creates CommandSource."""
        sources = {
            "shell_notes": {
                "type": "command",
                "enabled": True,
                "command": "echo 'test'",
                "prompt_hint": "{content}",
            },
        }
        config = MagicMock()
        config.context_sources = sources
        console = MagicMock()

        manager = ContextSourceManager(config, console)

        assert "shell_notes" in manager.sources
        assert isinstance(manager.sources["shell_notes"], CommandSource)

    @pytest.mark.asyncio
    async def test_command_source_in_build_context(self):
        """Test that command source content is included in context."""
        sources = {
            "notes": {
                "type": "command",
                "enabled": True,
                "command": "echo 'My notes content'",
                "prompt_hint": "<notes>\n{content}\n</notes>",
            },
        }
        config = MagicMock()
        config.context_sources = sources
        console = MagicMock()
        storage = MagicMock()

        manager = ContextSourceManager(config, console)
        await manager.initialize()
        context, warnings = await manager.build_context(storage)

        assert "<notes>" in context
        assert "My notes content" in context
