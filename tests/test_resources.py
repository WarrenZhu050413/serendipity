"""Tests for serendipity resources module."""

import pytest

from serendipity.resources import (
    get_approach_template,
    get_base_template,
    get_config_template,
    get_default_config,
    get_default_settings_yaml,
    get_discovery_prompt,
    get_loader_source_template,
    get_mcp_source_template,
    get_media_template,
    get_prompt,
    get_template,
)


class TestGetTemplate:
    """Tests for get_template function."""

    def test_get_base_template(self):
        """Test loading base.html template."""
        template = get_template("base.html")
        assert template is not None
        assert len(template) > 0
        # Should contain HTML structure
        assert "<!DOCTYPE html>" in template or "<html" in template

    def test_get_base_template_has_placeholders(self):
        """Test that base template has expected placeholders."""
        template = get_template("base.html")
        # Should have CSS placeholder
        assert "{css}" in template
        # Should have recommendations placeholder
        assert "{recommendations_html}" in template
        # Should have session ID placeholder
        assert "{session_id}" in template

    def test_get_base_template_convenience(self):
        """Test get_base_template convenience function."""
        template = get_base_template()
        assert template == get_template("base.html")

    def test_template_loads_consistently(self):
        """Test that template loading returns consistent content."""
        # Call twice - content should match (not cached, but same file)
        template1 = get_template("base.html")
        template2 = get_template("base.html")
        assert template1 == template2


class TestGetPrompt:
    """Tests for get_prompt function."""

    def test_get_discovery_prompt(self):
        """Test loading discovery.txt prompt."""
        prompt = get_prompt("discovery.txt")
        assert prompt is not None
        assert len(prompt) > 0

    def test_discovery_prompt_has_placeholders(self):
        """Test that discovery prompt has expected placeholders."""
        prompt = get_prompt("discovery.txt")
        # Should have user context placeholder
        assert "{user_context}" in prompt
        # Should have type guidance placeholder
        assert "{type_guidance}" in prompt

    def test_get_discovery_prompt_convenience(self):
        """Test get_discovery_prompt convenience function."""
        prompt = get_discovery_prompt()
        assert prompt == get_prompt("discovery.txt")

    def test_prompt_loads_consistently(self):
        """Test that prompt loading returns consistent content."""
        prompt1 = get_prompt("discovery.txt")
        prompt2 = get_prompt("discovery.txt")
        assert prompt1 == prompt2


class TestGetDefaultConfig:
    """Tests for get_default_config function."""

    def test_get_default_settings_yaml(self):
        """Test loading default settings.yaml."""
        config = get_default_config("settings.yaml")
        assert config is not None
        assert len(config) > 0
        # Should be valid YAML content
        assert "version:" in config

    def test_get_default_settings_yaml_has_sections(self):
        """Test that default settings has expected sections."""
        config = get_default_config("settings.yaml")
        # Should have model
        assert "model:" in config
        # Should have approaches
        assert "approaches:" in config
        # Should have media types
        assert "media:" in config
        # Should have context sources
        assert "context_sources:" in config

    def test_get_default_settings_yaml_convenience(self):
        """Test get_default_settings_yaml convenience function."""
        config = get_default_settings_yaml()
        assert config == get_default_config("settings.yaml")

    def test_config_loads_consistently(self):
        """Test that config loading returns consistent content."""
        config1 = get_default_config("settings.yaml")
        config2 = get_default_config("settings.yaml")
        assert config1 == config2


class TestResourcesIntegration:
    """Integration tests for resources module."""

    def test_all_resources_loadable(self):
        """Test that all expected resources can be loaded."""
        # Templates
        base_template = get_base_template()
        assert base_template

        # Prompts
        discovery_prompt = get_discovery_prompt()
        assert discovery_prompt

        # Config
        settings = get_default_settings_yaml()
        assert settings

    def test_template_and_prompt_compatible(self):
        """Test that template and prompt work together."""
        template = get_base_template()
        prompt = get_discovery_prompt()

        # Prompt should have user context and type guidance placeholders
        assert "{user_context}" in prompt
        assert "{type_guidance}" in prompt
        # Template should have the placeholders the system expects
        assert "{css}" in template
        assert "{recommendations_html}" in template

    def test_settings_yaml_parseable(self):
        """Test that default settings.yaml can be parsed."""
        import yaml

        settings_yaml = get_default_settings_yaml()
        # Should parse without error
        settings = yaml.safe_load(settings_yaml)
        assert isinstance(settings, dict)
        assert "version" in settings
        assert "approaches" in settings
        assert "media" in settings

    def test_settings_yaml_has_default_approaches(self):
        """Test that settings has default approaches."""
        import yaml

        settings = yaml.safe_load(get_default_settings_yaml())
        approaches = settings.get("approaches", {})
        assert "convergent" in approaches
        assert "divergent" in approaches

    def test_settings_yaml_has_default_media(self):
        """Test that settings has default media types."""
        import yaml

        settings = yaml.safe_load(get_default_settings_yaml())
        media = settings.get("media", {})
        assert "article" in media
        assert "youtube" in media
        assert "book" in media
        assert "podcast" in media

    def test_settings_yaml_has_context_sources(self):
        """Test that settings has context sources."""
        import yaml

        settings = yaml.safe_load(get_default_settings_yaml())
        context_sources = settings.get("context_sources", {})
        # Should have loader sources
        assert "taste" in context_sources
        assert context_sources["taste"]["type"] == "loader"
        # Should have MCP sources
        assert "whorl" in context_sources
        assert context_sources["whorl"]["type"] == "mcp"


class TestGetConfigTemplate:
    """Tests for get_config_template and convenience functions."""

    def test_get_media_template(self):
        """Test loading media template."""
        template = get_media_template()
        assert template is not None
        assert len(template) > 0
        # Should have placeholders
        assert "{display_name}" in template
        assert "{search_hints}" in template
        assert "{prompt_hint}" in template

    def test_get_approach_template(self):
        """Test loading approach template."""
        template = get_approach_template()
        assert template is not None
        assert "{display_name}" in template
        assert "{prompt_hint}" in template

    def test_get_loader_source_template(self):
        """Test loading loader source template."""
        template = get_loader_source_template()
        assert template is not None
        assert "type: loader" in template
        assert "{description}" in template
        assert "{path}" in template
        assert "{name}" in template

    def test_get_mcp_source_template(self):
        """Test loading MCP source template."""
        template = get_mcp_source_template()
        assert template is not None
        assert "type: mcp" in template
        assert "{description}" in template
        assert "{server_url}" in template
        assert "health_check" in template
        assert "auto_start" in template

    def test_get_config_template_directly(self):
        """Test get_config_template with filename."""
        template = get_config_template("media.yaml")
        assert template == get_media_template()

    def test_media_template_is_valid_yaml(self):
        """Test that media template produces valid YAML."""
        import yaml

        template = get_media_template()
        filled = template.format(
            display_name="Test Media",
            search_hints="{query} test",
            prompt_hint="Test hint",
        )
        parsed = yaml.safe_load(filled)
        assert parsed["display_name"] == "Test Media"
        assert parsed["enabled"] is True

    def test_approach_template_is_valid_yaml(self):
        """Test that approach template produces valid YAML."""
        import yaml

        template = get_approach_template()
        filled = template.format(
            display_name="Test Approach",
            prompt_hint="- Find cool stuff",
        )
        parsed = yaml.safe_load(filled)
        assert parsed["display_name"] == "Test Approach"
        assert "cool stuff" in parsed["prompt_hint"]

    def test_loader_template_is_valid_yaml(self):
        """Test that loader source template produces valid YAML."""
        import yaml

        template = get_loader_source_template()
        filled = template.format(
            name="test",
            description="Test source",
            path="~/test.md",
        )
        parsed = yaml.safe_load(filled)
        assert parsed["type"] == "loader"
        assert parsed["description"] == "Test source"
        assert parsed["options"]["path"] == "~/test.md"

    def test_mcp_template_is_valid_yaml(self):
        """Test that MCP source template produces valid YAML."""
        import yaml

        template = get_mcp_source_template()
        filled = template.format(
            name="test",
            description="Test MCP",
            server_url="http://localhost:8080/mcp/",
            cli_command="testcmd",
            port=8080,
            prompt_hint="Test",
        )
        parsed = yaml.safe_load(filled)
        assert parsed["type"] == "mcp"
        assert parsed["port"]["default"] == 8080
