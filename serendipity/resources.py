"""Resource loading utilities for serendipity.

Uses importlib.resources for robust package data access that works
whether installed normally, editable, or bundled.
"""

from functools import lru_cache
from importlib.resources import files


@lru_cache
def get_template(name: str) -> str:
    """Load a template file from serendipity/templates/.

    Args:
        name: Template filename (e.g., "base.html")

    Returns:
        Template content as string
    """
    return files("serendipity.templates").joinpath(name).read_text()


@lru_cache
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


def get_discovery_prompt() -> str:
    """Get the discovery prompt template."""
    return get_prompt("discovery.txt")


def get_frontend_design() -> str:
    """Get the frontend design guidelines."""
    try:
        return get_prompt("frontend_design.txt")
    except FileNotFoundError:
        return ""


@lru_cache
def get_default_config(name: str) -> str:
    """Load a default config file from serendipity/config/defaults/.

    Args:
        name: Config filename (e.g., "types.yaml")

    Returns:
        Config content as string
    """
    return files("serendipity.config.defaults").joinpath(name).read_text()


def get_default_types_yaml() -> str:
    """Get the default types.yaml configuration."""
    return get_default_config("types.yaml")
