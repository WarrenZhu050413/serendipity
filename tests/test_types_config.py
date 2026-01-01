"""Tests for serendipity.config.types."""

import tempfile
from pathlib import Path

import pytest

from serendipity.config.types import (
    ApproachType,
    MediaType,
    MetadataField,
    Source,
    TypesConfig,
)


class TestSource:
    """Test Source dataclass."""

    def test_creation(self):
        """Test creating a source."""
        source = Source(tool="WebSearch", hints="site:youtube.com {query}")
        assert source.tool == "WebSearch"
        assert source.hints == "site:youtube.com {query}"

    def test_default_hints(self):
        """Test source with default empty hints."""
        source = Source(tool="WebFetch")
        assert source.tool == "WebFetch"
        assert source.hints == ""


class TestMetadataField:
    """Test MetadataField dataclass."""

    def test_creation(self):
        """Test creating a metadata field."""
        field = MetadataField(name="author", required=True)
        assert field.name == "author"
        assert field.required is True

    def test_default_required(self):
        """Test default required is False."""
        field = MetadataField(name="year")
        assert field.required is False


class TestApproachType:
    """Test ApproachType dataclass."""

    def test_creation(self):
        """Test creating an approach type."""
        approach = ApproachType(
            name="convergent",
            display_name="More Like This",
            enabled=True,
            prompt_hint="Match their interests",
        )
        assert approach.name == "convergent"
        assert approach.display_name == "More Like This"
        assert approach.prompt_hint == "Match their interests"

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "display_name": "Expand",
            "enabled": True,
            "prompt_hint": "Be creative",
        }
        approach = ApproachType.from_dict("divergent", data)
        assert approach.name == "divergent"
        assert approach.display_name == "Expand"
        assert approach.prompt_hint == "Be creative"

    def test_from_dict_defaults(self):
        """Test from_dict with minimal data uses defaults."""
        data = {}
        approach = ApproachType.from_dict("test", data)
        assert approach.name == "test"
        assert approach.display_name == "Test"  # capitalized name
        assert approach.enabled is True


class TestMediaType:
    """Test MediaType dataclass."""

    def test_creation(self):
        """Test creating a media type."""
        media = MediaType(
            name="youtube",
            display_name="YouTube Videos",
            preference="I love video essays",
            sources=[Source(tool="WebSearch", hints="site:youtube.com")],
            metadata_schema=[MetadataField(name="channel", required=True)],
        )
        assert media.name == "youtube"
        assert media.preference == "I love video essays"
        assert len(media.sources) == 1
        assert media.sources[0].tool == "WebSearch"
        assert len(media.metadata_schema) == 1

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "display_name": "Books",
            "preference": "Want more of these",
            "sources": [
                {"tool": "WebSearch", "hints": "site:goodreads.com"},
            ],
            "metadata_schema": [
                {"name": "author", "required": True},
                {"name": "year", "required": False},
            ],
            "prompt_hint": "Mix fiction and non-fiction",
        }
        media = MediaType.from_dict("book", data)
        assert media.name == "book"
        assert media.display_name == "Books"
        assert media.preference == "Want more of these"
        assert len(media.sources) == 1
        assert media.sources[0].hints == "site:goodreads.com"
        assert len(media.metadata_schema) == 2
        assert media.metadata_schema[0].name == "author"
        assert media.metadata_schema[0].required is True

    def test_from_dict_defaults(self):
        """Test from_dict with minimal data."""
        data = {}
        media = MediaType.from_dict("article", data)
        assert media.name == "article"
        assert media.display_name == "Article"
        assert media.enabled is True
        assert media.preference == ""
        assert media.sources == []
        assert media.metadata_schema == []


class TestTypesConfig:
    """Test TypesConfig dataclass."""

    def test_default(self):
        """Test default configuration."""
        config = TypesConfig.default()
        assert config.version == 2  # Current version from defaults/settings.yaml
        assert config.model == "opus"
        assert config.feedback_server_port == 9876
        assert "convergent" in config.approaches
        assert "divergent" in config.approaches
        assert "article" in config.media
        assert "youtube" in config.media
        assert "book" in config.media
        assert config.total_count == 10
        # Also check context sources are loaded from defaults
        assert "taste" in config.context_sources
        assert "whorl" in config.context_sources

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "version": 2,
            "model": "sonnet",
            "approaches": {
                "convergent": {
                    "display_name": "Similar",
                },
            },
            "media": {
                "podcast": {
                    "display_name": "Podcasts",
                    "preference": "I love podcasts",
                },
            },
            "total_count": 5,
        }
        config = TypesConfig.from_dict(data)
        assert config.version == 2
        assert config.model == "sonnet"
        assert len(config.approaches) == 1
        assert config.approaches["convergent"].display_name == "Similar"
        assert len(config.media) == 1
        assert config.media["podcast"].preference == "I love podcasts"
        assert config.total_count == 5

    def test_get_enabled_approaches(self):
        """Test filtering enabled approaches."""
        config = TypesConfig.default()
        enabled = config.get_enabled_approaches()
        assert len(enabled) == 2
        assert all(a.enabled for a in enabled)

    def test_get_enabled_approaches_filters_disabled(self):
        """Test that disabled approaches are filtered out."""
        config = TypesConfig.default()
        config.approaches["convergent"].enabled = False
        enabled = config.get_enabled_approaches()
        assert len(enabled) == 1
        assert enabled[0].name == "divergent"

    def test_get_enabled_media(self):
        """Test filtering enabled media types."""
        config = TypesConfig.default()
        enabled = config.get_enabled_media()
        assert len(enabled) == 4  # article, youtube, book, podcast
        assert all(m.enabled for m in enabled)

    def test_from_yaml(self):
        """Test loading from YAML file."""
        yaml_content = """
version: 2
model: haiku
approaches:
  test_approach:
    display_name: "Test"
media:
  test_media:
    display_name: "Test Media"
total_count: 5
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            path = Path(f.name)

        try:
            config = TypesConfig.from_yaml(path)
            assert "test_approach" in config.approaches
            assert "test_media" in config.media
            assert config.total_count == 5
            assert config.model == "haiku"
        finally:
            path.unlink()

    def test_from_yaml_nonexistent_creates_default(self, tmp_path):
        """Test that missing YAML file creates default config."""
        yaml_path = tmp_path / "settings.yaml"
        assert not yaml_path.exists()

        config = TypesConfig.from_yaml(yaml_path)

        # Should create the file
        assert yaml_path.exists()
        # Should return default config
        assert "convergent" in config.approaches
        assert "divergent" in config.approaches
        assert "taste" in config.context_sources


class TestTypesConfigIntegration:
    """Integration tests for TypesConfig."""

    def test_all_approaches_enabled_by_default(self):
        """Test that all default approaches are enabled."""
        config = TypesConfig.default()
        assert all(a.enabled for a in config.approaches.values())

    def test_all_media_enabled_by_default(self):
        """Test that all default media types are enabled."""
        config = TypesConfig.default()
        assert all(m.enabled for m in config.media.values())

    def test_context_sources_have_correct_types(self):
        """Test that context sources have the correct types."""
        config = TypesConfig.default()
        # Loader sources
        assert config.context_sources["taste"].type == "loader"
        assert config.context_sources["learnings"].type == "loader"
        # MCP sources
        assert config.context_sources["whorl"].type == "mcp"


class TestVariableExpansion:
    """Tests for template variable expansion."""

    def test_expand_string(self):
        """Test expanding variables in a string."""
        from serendipity.config.types import expand_variables

        context = {"profile_dir": "/path/to/profile", "home": "/home/user"}
        result = expand_variables("{profile_dir}/taste.md", context)

        assert result == "/path/to/profile/taste.md"

    def test_expand_multiple_variables(self):
        """Test expanding multiple variables in one string."""
        from serendipity.config.types import expand_variables

        context = {"profile_dir": "/profiles/work", "profile_name": "work"}
        result = expand_variables("{profile_dir}/{profile_name}.log", context)

        assert result == "/profiles/work/work.log"

    def test_expand_in_dict(self):
        """Test expanding variables in nested dict."""
        from serendipity.config.types import expand_variables

        context = {"profile_dir": "/my/profile"}
        data = {
            "path": "{profile_dir}/file.md",
            "nested": {
                "inner": "{profile_dir}/nested.md"
            }
        }

        result = expand_variables(data, context)

        assert result["path"] == "/my/profile/file.md"
        assert result["nested"]["inner"] == "/my/profile/nested.md"

    def test_expand_in_list(self):
        """Test expanding variables in list."""
        from serendipity.config.types import expand_variables

        context = {"home": "/users/me"}
        data = ["{home}/a.md", "{home}/b.md"]

        result = expand_variables(data, context)

        assert result == ["/users/me/a.md", "/users/me/b.md"]

    def test_unknown_variable_unchanged(self):
        """Test that unknown variables are left unchanged."""
        from serendipity.config.types import expand_variables

        context = {"known": "value"}
        result = expand_variables("{unknown}/path", context)

        assert result == "{unknown}/path"

    def test_non_string_unchanged(self):
        """Test that non-string values pass through unchanged."""
        from serendipity.config.types import expand_variables

        context = {"x": "y"}
        assert expand_variables(42, context) == 42
        assert expand_variables(True, context) is True
        assert expand_variables(None, context) is None

    def test_build_variable_context(self):
        """Test building context from profile info."""
        from pathlib import Path
        from serendipity.config.types import build_variable_context

        context = build_variable_context(
            profile_dir=Path("/profiles/test"),
            profile_name="test"
        )

        assert context["profile_dir"] == "/profiles/test"
        assert context["profile_name"] == "test"
        assert "home" in context

    def test_from_yaml_with_variable_context(self, tmp_path):
        """Test that from_yaml expands variables when context provided."""
        yaml_content = """
version: 2
context_sources:
  taste:
    type: loader
    enabled: true
    options:
      path: "{profile_dir}/taste.md"
"""
        path = tmp_path / "settings.yaml"
        path.write_text(yaml_content)

        context = {"profile_dir": "/my/profile", "home": "/home"}
        config = TypesConfig.from_yaml(path, variable_context=context)

        taste = config.context_sources.get("taste")
        assert taste is not None
        assert taste.raw_config["options"]["path"] == "/my/profile/taste.md"
