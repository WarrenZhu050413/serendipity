"""Resource loading utilities for serendipity.

Uses importlib.resources for robust package data access that works
whether installed normally, editable, or bundled.
"""

from importlib.resources import files


def get_template(name: str) -> str:
    """Load a template file from serendipity/templates/.

    Args:
        name: Template filename (e.g., "base.html")

    Returns:
        Template content as string
    """
    return files("serendipity.templates").joinpath(name).read_text()


def get_prompt(name: str) -> str:
    """Load a prompt file from serendipity/prompts/.

    Args:
        name: Prompt filename (e.g., "discovery.txt")

    Returns:
        Prompt content as string
    """
    return files("serendipity.prompts").joinpath(name).read_text()


# Convenience constants for common resources
def get_base_template() -> str:
    """Get the base HTML template."""
    return get_template("base.html")


def get_default_style() -> str:
    """Get the default CSS stylesheet."""
    return get_template("style.css")


def get_discovery_prompt() -> str:
    """Get the discovery prompt template."""
    return get_prompt("discovery.txt")


def get_frontend_design() -> str:
    """Get the frontend design guidelines."""
    try:
        return get_prompt("frontend_design.txt")
    except FileNotFoundError:
        return ""


def get_system_prompt() -> str:
    """Get the system prompt for the agent."""
    return get_prompt("system.txt")


def get_default_config(name: str) -> str:
    """Load a default config file from serendipity/config/defaults/.

    Args:
        name: Config filename (e.g., "settings.yaml")

    Returns:
        Config content as string
    """
    return files("serendipity.config.defaults").joinpath(name).read_text()


def get_default_settings_yaml() -> str:
    """Get the default settings.yaml configuration."""
    return get_default_config("settings.yaml")


def get_config_template(name: str) -> str:
    """Load a config template file from serendipity/config/templates/.

    Args:
        name: Template filename (e.g., "media.yaml", "approach.yaml",
              "loader_source.yaml", "mcp_source.yaml")

    Returns:
        Template content as string
    """
    return files("serendipity.config.templates").joinpath(name).read_text()


def get_media_template() -> str:
    """Get the media type template."""
    return get_config_template("media.yaml")


def get_approach_template() -> str:
    """Get the approach type template."""
    return get_config_template("approach.yaml")


def get_loader_source_template() -> str:
    """Get the loader context source template."""
    return get_config_template("loader_source.yaml")


def get_mcp_source_template() -> str:
    """Get the MCP context source template."""
    return get_config_template("mcp_source.yaml")
