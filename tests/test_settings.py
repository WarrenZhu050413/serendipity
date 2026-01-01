"""Tests for serendipity settings module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from serendipity import settings as settings_module


class TestSettingsModule:
    """Tests for settings.py functions."""

    @pytest.fixture
    def temp_settings_dir(self, monkeypatch):
        """Create a temp directory and patch StorageManager to use it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            settings_path = tmpdir_path / "settings.yaml"

            # Patch get_user_settings_path to use temp path
            monkeypatch.setattr(
                settings_module,
                "get_user_settings_path",
                lambda: settings_path
            )
            yield tmpdir_path, settings_path

    def test_load_user_settings_empty(self, temp_settings_dir):
        """Test loading settings when file doesn't exist."""
        _, settings_path = temp_settings_dir
        assert not settings_path.exists()

        result = settings_module.load_user_settings()
        assert result == {}

    def test_load_user_settings_existing(self, temp_settings_dir):
        """Test loading settings from existing file."""
        _, settings_path = temp_settings_dir
        settings_path.write_text("model: opus\ntotal_count: 15\n")

        result = settings_module.load_user_settings()
        assert result["model"] == "opus"
        assert result["total_count"] == 15

    def test_save_user_settings(self, temp_settings_dir):
        """Test saving settings to file."""
        _, settings_path = temp_settings_dir
        data = {"model": "haiku", "total_count": 5}

        settings_module.save_user_settings(data)

        assert settings_path.exists()
        loaded = yaml.safe_load(settings_path.read_text())
        assert loaded["model"] == "haiku"
        assert loaded["total_count"] == 5


class TestAddMedia:
    """Tests for add_media function."""

    @pytest.fixture
    def temp_settings(self, monkeypatch):
        """Create temp settings file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.yaml"
            monkeypatch.setattr(
                settings_module,
                "get_user_settings_path",
                lambda: settings_path
            )
            yield settings_path

    def test_add_media_basic(self, temp_settings):
        """Test adding a basic media type."""
        result = settings_module.add_media(
            name="papers",
            display_name="Academic Papers",
        )

        assert result["display_name"] == "Academic Papers"
        assert result["enabled"] is True
        assert "sources" in result

        # Verify it was saved
        saved = yaml.safe_load(temp_settings.read_text())
        assert "media" in saved
        assert "papers" in saved["media"]

    def test_add_media_with_hints(self, temp_settings):
        """Test adding media with custom search hints."""
        result = settings_module.add_media(
            name="papers",
            display_name="Papers",
            search_hints="site:arxiv.org {query}",
        )

        assert result["sources"][0]["hints"] == "site:arxiv.org {query}"

    def test_add_media_with_prompt_hint(self, temp_settings):
        """Test adding media with custom prompt hint."""
        result = settings_module.add_media(
            name="papers",
            display_name="Papers",
            prompt_hint="Focus on peer-reviewed content.",
        )

        assert "peer-reviewed" in result["prompt_hint"]

    def test_add_media_auto_display_name(self, temp_settings):
        """Test that display name is auto-generated from name."""
        result = settings_module.add_media(name="academic_papers")

        assert result["display_name"] == "Academic Papers"

    def test_add_media_disabled(self, temp_settings):
        """Test adding disabled media type."""
        result = settings_module.add_media(
            name="papers",
            display_name="Papers",
            enabled=False,
        )

        assert result["enabled"] is False


class TestAddApproach:
    """Tests for add_approach function."""

    @pytest.fixture
    def temp_settings(self, monkeypatch):
        """Create temp settings file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.yaml"
            monkeypatch.setattr(
                settings_module,
                "get_user_settings_path",
                lambda: settings_path
            )
            yield settings_path

    def test_add_approach_basic(self, temp_settings):
        """Test adding a basic approach."""
        result = settings_module.add_approach(
            name="lucky",
            display_name="Pure Luck",
        )

        assert result["display_name"] == "Pure Luck"
        assert result["enabled"] is True
        assert "prompt_hint" in result

        # Verify it was saved
        saved = yaml.safe_load(temp_settings.read_text())
        assert "approaches" in saved
        assert "lucky" in saved["approaches"]

    def test_add_approach_with_hint(self, temp_settings):
        """Test adding approach with custom prompt hint."""
        result = settings_module.add_approach(
            name="random",
            display_name="Random",
            prompt_hint="- Pick content completely at random",
        )

        assert "random" in result["prompt_hint"]

    def test_add_approach_auto_display_name(self, temp_settings):
        """Test that display name is auto-generated."""
        result = settings_module.add_approach(name="pure_serendipity")

        assert result["display_name"] == "Pure Serendipity"


class TestAddLoaderSource:
    """Tests for add_loader_source function."""

    @pytest.fixture
    def temp_settings(self, monkeypatch):
        """Create temp settings file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.yaml"
            monkeypatch.setattr(
                settings_module,
                "get_user_settings_path",
                lambda: settings_path
            )
            yield settings_path

    def test_add_loader_source_basic(self, temp_settings):
        """Test adding a basic loader source."""
        result = settings_module.add_loader_source(
            name="notes",
            path="~/.serendipity/notes.md",
        )

        assert result["type"] == "loader"
        assert result["enabled"] is True
        assert result["options"]["path"] == "~/.serendipity/notes.md"
        assert "file_loader" in result["loader"]

        # Verify saved
        saved = yaml.safe_load(temp_settings.read_text())
        assert "context_sources" in saved
        assert "notes" in saved["context_sources"]

    def test_add_loader_source_with_description(self, temp_settings):
        """Test adding loader source with description."""
        result = settings_module.add_loader_source(
            name="notes",
            path="~/notes.md",
            description="My personal notes",
        )

        assert result["description"] == "My personal notes"

    def test_add_loader_source_prompt_hint_contains_name(self, temp_settings):
        """Test that prompt hint contains the source name as XML tags."""
        result = settings_module.add_loader_source(
            name="custom",
            path="~/custom.md",
        )

        assert "<custom>" in result["prompt_hint"]
        assert "</custom>" in result["prompt_hint"]


class TestAddMCPSource:
    """Tests for add_mcp_source function."""

    @pytest.fixture
    def temp_settings(self, monkeypatch):
        """Create temp settings file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.yaml"
            monkeypatch.setattr(
                settings_module,
                "get_user_settings_path",
                lambda: settings_path
            )
            yield settings_path

    def test_add_mcp_source_basic(self, temp_settings):
        """Test adding a basic MCP source."""
        result = settings_module.add_mcp_source(name="custom")

        assert result["type"] == "mcp"
        assert result["enabled"] is False  # MCP disabled by default
        assert "health_check" in result
        assert "port" in result
        assert "auto_start" in result

    def test_add_mcp_source_with_options(self, temp_settings):
        """Test adding MCP source with custom options."""
        result = settings_module.add_mcp_source(
            name="custom",
            server_url="http://localhost:9999/mcp/",
            cli_command="mycmd",
            port=9999,
        )

        assert "9999" in result["server"]["url"]
        assert result["port"]["default"] == 9999
        assert "mycmd" in result["auto_start"]["command"]

    def test_add_mcp_source_enabled(self, temp_settings):
        """Test adding enabled MCP source."""
        result = settings_module.add_mcp_source(
            name="custom",
            enabled=True,
        )

        assert result["enabled"] is True


class TestAddSource:
    """Tests for add_source dispatcher function."""

    @pytest.fixture
    def temp_settings(self, monkeypatch):
        """Create temp settings file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.yaml"
            monkeypatch.setattr(
                settings_module,
                "get_user_settings_path",
                lambda: settings_path
            )
            yield settings_path

    def test_add_source_loader(self, temp_settings):
        """Test dispatcher routes to loader."""
        result = settings_module.add_source(
            name="notes",
            source_type="loader",
            path="~/notes.md",
        )

        assert result["type"] == "loader"

    def test_add_source_mcp(self, temp_settings):
        """Test dispatcher routes to mcp."""
        result = settings_module.add_source(
            name="custom",
            source_type="mcp",
        )

        assert result["type"] == "mcp"

    def test_add_source_invalid_type(self, temp_settings):
        """Test dispatcher raises on invalid type."""
        with pytest.raises(ValueError, match="Unknown source type"):
            settings_module.add_source(
                name="test",
                source_type="invalid",
            )
