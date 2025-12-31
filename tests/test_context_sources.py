"""Tests for serendipity context sources module."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from serendipity.context_sources import (
    ContextResult,
    ContextSourceManager,
    LoaderSource,
    MCPConfig,
    MCPServerSource,
)
from serendipity.context_sources.builtins import (
    file_loader,
    history_loader,
    style_loader,
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
        storage.load_config.return_value.history_enabled = True
        storage.load_learnings.return_value = ""
        storage.load_recent_history.return_value = []
        storage.get_unextracted_entries.return_value = []

        content, warnings = history_loader(storage, {})
        assert content == ""
        assert warnings == []

    def test_history_loader_disabled(self):
        """Test history_loader with history disabled."""
        storage = MagicMock()
        storage.load_config.return_value.history_enabled = False

        content, warnings = history_loader(storage, {})
        assert content == ""
        assert warnings == []

    def test_history_loader_with_learnings(self):
        """Test history_loader with learnings."""
        storage = MagicMock()
        storage.load_config.return_value.history_enabled = True
        storage.load_learnings.return_value = "## Likes\n### Test\nI like this"
        storage.load_recent_history.return_value = []
        storage.get_unextracted_entries.return_value = []

        content, warnings = history_loader(storage, {})
        assert "<discovery_learnings>" in content
        assert "I like this" in content

    def test_style_loader_custom(self):
        """Test style_loader with custom style."""
        storage = MagicMock()
        storage.load_config.return_value.html_style = "dark mode minimal"

        content, warnings = style_loader(storage, {})
        assert "dark mode minimal" in content
        assert warnings == []

    def test_style_loader_default(self):
        """Test style_loader with default style."""
        storage = MagicMock()
        storage.load_config.return_value.html_style = None

        content, warnings = style_loader(storage, {})
        assert "aesthetic taste" in content
        assert warnings == []


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
