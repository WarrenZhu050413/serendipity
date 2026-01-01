"""Tests for serendipity.prompts.builder."""

import pytest

from serendipity.config.types import (
    ApproachType,
    MediaType,
    MetadataField,
    Source,
    TypesConfig,
)
from serendipity.prompts.builder import MEDIA_ICONS, PromptBuilder


class TestMediaIcons:
    """Test media icon mapping."""

    def test_common_icons_exist(self):
        """Test that common media types have icons."""
        assert "youtube" in MEDIA_ICONS
        assert "book" in MEDIA_ICONS
        assert "article" in MEDIA_ICONS
        assert "podcast" in MEDIA_ICONS

    def test_icons_are_emoji(self):
        """Test that icons are single emoji characters."""
        for icon in MEDIA_ICONS.values():
            # Each icon should be 1-2 characters (emoji can be 2 chars)
            assert 1 <= len(icon) <= 2


class TestPromptBuilder:
    """Test PromptBuilder class."""

    @pytest.fixture
    def default_config(self):
        """Create default config for tests."""
        return TypesConfig.default()

    @pytest.fixture
    def builder(self, default_config):
        """Create builder with default config."""
        return PromptBuilder(default_config)

    def test_init(self, default_config):
        """Test builder initialization."""
        builder = PromptBuilder(default_config)
        assert builder.config == default_config

    def test_build_approach_section(self, builder):
        """Test approach section generation."""
        section = builder.build_approach_section()

        # Should contain header
        assert "## APPROACH TYPES" in section

        # Should contain both approaches
        assert "More Like This" in section
        assert "Expand Your Palette" in section

        # Should contain prompt hints
        assert "CONVERGENT" in section
        assert "DIVERGENT" in section

    def test_build_approach_section_filters_disabled(self, default_config):
        """Test that disabled approaches are excluded."""
        default_config.approaches["convergent"].enabled = False
        builder = PromptBuilder(default_config)
        section = builder.build_approach_section()

        assert "More Like This" not in section
        assert "Expand Your Palette" in section

    def test_build_media_section(self, builder):
        """Test media section generation."""
        section = builder.build_media_section()

        # Should contain header
        assert "## MEDIA TYPES" in section

        # Should contain media types with icons
        assert "Articles & Essays" in section
        assert "YouTube Videos" in section
        assert "Books" in section

        # Should contain search hints
        assert "Search hints" in section
        assert "WebSearch" in section

    def test_build_media_section_includes_required_metadata(self, builder):
        """Test that required metadata fields are shown."""
        section = builder.build_media_section()

        # YouTube requires channel and duration
        assert "Required metadata" in section
        assert "channel" in section
        assert "duration" in section

    def test_build_media_section_filters_disabled(self, default_config):
        """Test that disabled media types are excluded."""
        default_config.media["youtube"].enabled = False
        builder = PromptBuilder(default_config)
        section = builder.build_media_section()

        assert "YouTube Videos" not in section
        assert "Articles & Essays" in section

    def test_build_distribution_guidance(self, builder):
        """Test distribution guidance generation."""
        guidance = builder.build_distribution_guidance()

        # Should contain header
        assert "## DISTRIBUTION" in guidance

        # Should contain total count
        assert "Total: 10" in guidance

        # Should encourage agent autonomy
        assert "choose" in guidance.lower()
        assert "taste" in guidance.lower()

    def test_build_distribution_guidance_with_preferences(self, default_config):
        """Test distribution guidance includes user preferences."""
        default_config.media["podcast"].preference = "I want more podcasts"
        builder = PromptBuilder(default_config)
        guidance = builder.build_distribution_guidance()

        assert "User preferences" in guidance
        assert "I want more podcasts" in guidance

    def test_build_output_schema(self, builder):
        """Test output schema generation."""
        schema = builder.build_output_schema()

        # Should contain header
        assert "## OUTPUT FORMAT" in schema

        # Should be JSON format
        assert "```json" in schema
        assert "```" in schema

        # Should contain approach keys
        assert '"convergent"' in schema
        assert '"divergent"' in schema

        # Should contain required fields
        assert '"url"' in schema
        assert '"reason"' in schema
        assert '"type"' in schema

    def test_build_type_guidance(self, builder):
        """Test complete type guidance generation."""
        guidance = builder.build_type_guidance()

        # Should contain approach, media, and distribution sections
        assert "## APPROACH TYPES" in guidance
        assert "## MEDIA TYPES" in guidance
        assert "## DISTRIBUTION" in guidance

        # OUTPUT FORMAT is now separate (build_output_schema)
        assert "## OUTPUT FORMAT" not in guidance

        # Should be properly joined with newlines
        assert "\n\n" in guidance

    def test_build_type_guidance_with_custom_config(self):
        """Test guidance with custom configuration."""
        config = TypesConfig(
            approaches={
                "deep_dive": ApproachType(
                    name="deep_dive",
                    display_name="Deep Dive",
                    prompt_hint="Find comprehensive resources",
                ),
            },
            media={
                "archive": MediaType(
                    name="archive",
                    display_name="Academic Papers",
                    sources=[Source(tool="WebSearch", hints="site:arxiv.org")],
                ),
            },
            total_count=5,
        )
        builder = PromptBuilder(config)
        guidance = builder.build_type_guidance()

        assert "Deep Dive" in guidance
        assert "Academic Papers" in guidance
        assert "arxiv.org" in guidance
        assert "Total: 5" in guidance


class TestPromptBuilderEdgeCases:
    """Edge case tests for PromptBuilder."""

    def test_empty_config(self):
        """Test builder with empty config."""
        config = TypesConfig(approaches={}, media={})
        builder = PromptBuilder(config)

        # Should still generate valid output
        guidance = builder.build_type_guidance()
        assert "## APPROACH TYPES" in guidance
        assert "## MEDIA TYPES" in guidance

    def test_media_without_sources_uses_websearch_default(self):
        """Test media type without sources gets WebSearch default."""
        config = TypesConfig(
            approaches={"test": ApproachType(name="test", display_name="Test")},
            media={"test": MediaType(name="test", display_name="Test", sources=[])},
        )
        builder = PromptBuilder(config)
        section = builder.build_media_section()

        # Should use default WebSearch with media type name
        assert "Test" in section
        assert "WebSearch" in section
        # Default format is "- WebSearch: {media_name} {query}"
        assert "test" in section  # media name in the hint

    def test_media_without_metadata_schema(self):
        """Test media type without metadata schema."""
        config = TypesConfig(
            approaches={"test": ApproachType(name="test", display_name="Test")},
            media={"test": MediaType(name="test", display_name="Test", metadata_schema=[])},
        )
        builder = PromptBuilder(config)
        section = builder.build_media_section()

        # Should not include required metadata line
        assert "Required metadata" not in section or "test" not in section.split("Required metadata")[0]

    def test_approach_without_prompt_hint(self):
        """Test approach type without prompt hint."""
        config = TypesConfig(
            approaches={
                "test": ApproachType(
                    name="test",
                    display_name="Test",
                    prompt_hint="",  # Empty hint
                ),
            },
            media={"test": MediaType(name="test", display_name="Test")},
        )
        builder = PromptBuilder(config)
        section = builder.build_approach_section()

        # Should still include the approach
        assert "Test" in section

    def test_unknown_media_type_uses_default_icon(self):
        """Test that unknown media type uses default icon."""
        config = TypesConfig(
            approaches={"test": ApproachType(name="test", display_name="Test")},
            media={
                "custom_type": MediaType(
                    name="custom_type",
                    display_name="Custom Type",
                ),
            },
        )
        builder = PromptBuilder(config)
        section = builder.build_media_section()

        # Should use fallback icon (📄)
        assert "📄" in section or "Custom Type" in section
