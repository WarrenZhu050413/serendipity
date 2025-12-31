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
            description="Direct matches",
            enabled=True,
            weight=0.6,
            prompt_hint="Match their interests",
        )
        assert approach.name == "convergent"
        assert approach.display_name == "More Like This"
        assert approach.weight == 0.6

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "display_name": "Expand",
            "description": "Surprising content",
            "enabled": True,
            "weight": 0.4,
            "prompt_hint": "Be creative",
        }
        approach = ApproachType.from_dict("divergent", data)
        assert approach.name == "divergent"
        assert approach.display_name == "Expand"
        assert approach.weight == 0.4
        assert approach.prompt_hint == "Be creative"

    def test_from_dict_with_count(self):
        """Test from_dict with count instead of weight."""
        data = {
            "display_name": "Deep Dive",
            "description": "In-depth content",
            "count": 3,
        }
        approach = ApproachType.from_dict("deep_dive", data)
        assert approach.count == 3

    def test_from_dict_defaults(self):
        """Test from_dict with minimal data uses defaults."""
        data = {}
        approach = ApproachType.from_dict("test", data)
        assert approach.name == "test"
        assert approach.display_name == "Test"  # capitalized name
        assert approach.enabled is True
        assert approach.weight == 0.5


class TestMediaType:
    """Test MediaType dataclass."""

    def test_creation(self):
        """Test creating a media type."""
        media = MediaType(
            name="youtube",
            display_name="YouTube Videos",
            description="Video content",
            weight=0.25,
            sources=[Source(tool="WebSearch", hints="site:youtube.com")],
            metadata_schema=[MetadataField(name="channel", required=True)],
        )
        assert media.name == "youtube"
        assert media.weight == 0.25
        assert len(media.sources) == 1
        assert media.sources[0].tool == "WebSearch"
        assert len(media.metadata_schema) == 1

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "display_name": "Books",
            "description": "Books to read",
            "weight": 0.2,
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
        assert media.weight == 0.2
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
        assert media.weight == 0.2
        assert media.sources == []
        assert media.metadata_schema == []


class TestTypesConfig:
    """Test TypesConfig dataclass."""

    def test_default(self):
        """Test default configuration."""
        config = TypesConfig.default()
        assert config.version == 2  # Current version from defaults/types.yaml
        assert "convergent" in config.approaches
        assert "divergent" in config.approaches
        assert "article" in config.media
        assert "youtube" in config.media
        assert "book" in config.media
        assert config.total_count == 10
        assert config.agent_mode == "autonomous"
        # Also check context sources are loaded from defaults
        assert "taste" in config.context_sources
        assert "whorl" in config.context_sources

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "version": 2,
            "approaches": {
                "convergent": {
                    "display_name": "Similar",
                    "weight": 0.7,
                },
            },
            "media": {
                "podcast": {
                    "display_name": "Podcasts",
                    "weight": 1.0,
                },
            },
            "total_count": 5,
            "agent_mode": "strict",
        }
        config = TypesConfig.from_dict(data)
        assert config.version == 2
        assert len(config.approaches) == 1
        assert config.approaches["convergent"].weight == 0.7
        assert len(config.media) == 1
        assert config.total_count == 5
        assert config.agent_mode == "strict"

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

    def test_calculate_distribution(self):
        """Test distribution matrix calculation."""
        config = TypesConfig.default()
        matrix = config.calculate_distribution()

        # Should have both approaches
        assert "convergent" in matrix
        assert "divergent" in matrix

        # Each approach should have all media types
        assert "article" in matrix["convergent"]
        assert "youtube" in matrix["convergent"]
        assert "book" in matrix["convergent"]

        # Check total sums approximately to total_count
        total = sum(
            count
            for approach_counts in matrix.values()
            for count in approach_counts.values()
        )
        assert 9 <= total <= 11  # Allow for rounding

    def test_calculate_distribution_with_overrides(self):
        """Test distribution with weight overrides."""
        config = TypesConfig.default()
        config.overrides = {
            "convergent": {
                "youtube": {"weight": 0.5},  # Override to high weight
            }
        }
        matrix = config.calculate_distribution()

        # YouTube should have higher count for convergent
        assert matrix["convergent"]["youtube"] == 5.0  # 0.5 * 10

    def test_from_yaml(self):
        """Test loading from YAML file."""
        yaml_content = """
version: 1
approaches:
  test_approach:
    display_name: "Test"
    weight: 1.0
media:
  test_media:
    display_name: "Test Media"
    weight: 1.0
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
        finally:
            path.unlink()

    def test_from_yaml_nonexistent_creates_default(self, tmp_path):
        """Test that missing YAML file creates default config."""
        yaml_path = tmp_path / "types.yaml"
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

    def test_default_weights_sum_to_one(self):
        """Test that default approach weights sum to 1."""
        config = TypesConfig.default()
        total_weight = sum(a.weight for a in config.get_enabled_approaches())
        assert total_weight == 1.0

    def test_default_media_weights_sum_to_one(self):
        """Test that default media weights sum to 1."""
        config = TypesConfig.default()
        total_weight = sum(m.weight for m in config.get_enabled_media())
        assert total_weight == 1.0

    def test_distribution_covers_all_combinations(self):
        """Test that distribution includes all approach × media combinations."""
        config = TypesConfig.default()
        matrix = config.calculate_distribution()

        approaches = [a.name for a in config.get_enabled_approaches()]
        media_types = [m.name for m in config.get_enabled_media()]

        for approach in approaches:
            assert approach in matrix
            for media in media_types:
                assert media in matrix[approach]
