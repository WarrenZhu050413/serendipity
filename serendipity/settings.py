"""Settings management utilities for serendipity.

Functions for adding media types, approaches, and context sources
to the user's settings.yaml file.
"""

from pathlib import Path
from typing import Literal

import yaml

from serendipity.resources import (
    get_approach_template,
    get_loader_source_template,
    get_mcp_source_template,
    get_media_template,
)
from serendipity.storage import StorageManager


def get_user_settings_path() -> Path:
    """Get path to user's settings.yaml file."""
    storage = StorageManager()
    return storage.settings_path


def load_user_settings() -> dict:
    """Load user's settings.yaml, or empty dict if not exists."""
    path = get_user_settings_path()
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def save_user_settings(settings: dict) -> None:
    """Save settings to user's settings.yaml."""
    path = get_user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(settings, default_flow_style=False, sort_keys=False))


def add_media(
    name: str,
    display_name: str | None = None,
    search_hints: str = "{query}",
    prompt_hint: str = "",
    enabled: bool = True,
) -> dict:
    """Add a new media type to settings.

    Args:
        name: Internal name (e.g., "papers")
        display_name: User-facing name (e.g., "Academic Papers")
        search_hints: Search pattern template (default: "{query}")
        prompt_hint: Guidance for the agent
        enabled: Whether to enable immediately

    Returns:
        The new media config dict
    """
    if display_name is None:
        display_name = name.replace("_", " ").title()

    settings = load_user_settings()
    if "media" not in settings:
        settings["media"] = {}

    # Parse template and fill in values
    template = get_media_template()
    new_media = yaml.safe_load(
        template.format(
            name=name,
            display_name=display_name,
            search_hints=search_hints,
            prompt_hint=prompt_hint or f"Search for {display_name.lower()}.",
        )
    )
    new_media["enabled"] = enabled

    settings["media"][name] = new_media
    save_user_settings(settings)
    return new_media


def add_approach(
    name: str,
    display_name: str | None = None,
    prompt_hint: str = "",
    enabled: bool = True,
) -> dict:
    """Add a new approach type to settings.

    Args:
        name: Internal name (e.g., "serendipitous")
        display_name: User-facing name (e.g., "Pure Luck")
        prompt_hint: Guidance for this discovery style
        enabled: Whether to enable immediately

    Returns:
        The new approach config dict
    """
    if display_name is None:
        display_name = name.replace("_", " ").title()

    settings = load_user_settings()
    if "approaches" not in settings:
        settings["approaches"] = {}

    template = get_approach_template()
    new_approach = yaml.safe_load(
        template.format(
            name=name,
            display_name=display_name,
            prompt_hint=prompt_hint or "- Find unique and interesting content",
        )
    )
    new_approach["enabled"] = enabled

    settings["approaches"][name] = new_approach
    save_user_settings(settings)
    return new_approach


def add_loader_source(
    name: str,
    path: str,
    description: str | None = None,
    prompt_hint: str | None = None,
    enabled: bool = True,
) -> dict:
    """Add a new loader context source to settings.

    Args:
        name: Internal name (e.g., "notes")
        path: File path to load (supports ~)
        description: Human-readable description
        prompt_hint: Custom prompt template (optional)
        enabled: Whether to enable immediately

    Returns:
        The new source config dict
    """
    settings = load_user_settings()
    if "context_sources" not in settings:
        settings["context_sources"] = {}

    if description is None:
        description = f"Content from {name}"

    template = get_loader_source_template()
    new_source = yaml.safe_load(
        template.format(
            name=name,
            description=description,
            path=path,
        )
    )

    # Apply custom prompt hint if provided
    if prompt_hint:
        new_source["prompt_hint"] = prompt_hint

    new_source["enabled"] = enabled

    settings["context_sources"][name] = new_source
    save_user_settings(settings)
    return new_source


def add_mcp_source(
    name: str,
    server_url: str = "http://localhost:{port}/mcp/",
    cli_command: str | None = None,
    port: int = 8080,
    description: str | None = None,
    prompt_hint: str = "",
    enabled: bool = False,  # MCP sources disabled by default
) -> dict:
    """Add a new MCP context source to settings.

    Args:
        name: Internal name (e.g., "whorl")
        server_url: MCP server URL template
        cli_command: Command to start server (optional)
        port: Default port number
        description: Human-readable description
        prompt_hint: Guidance for using this source
        enabled: Whether to enable (default False for MCP)

    Returns:
        The new source config dict
    """
    settings = load_user_settings()
    if "context_sources" not in settings:
        settings["context_sources"] = {}

    if description is None:
        description = f"MCP server: {name}"
    if cli_command is None:
        cli_command = name

    template = get_mcp_source_template()
    new_source = yaml.safe_load(
        template.format(
            name=name,
            description=description,
            server_url=server_url,
            cli_command=cli_command,
            port=port,
            prompt_hint=prompt_hint,
        )
    )
    new_source["enabled"] = enabled

    settings["context_sources"][name] = new_source
    save_user_settings(settings)
    return new_source


def add_source(
    name: str,
    source_type: Literal["loader", "mcp"],
    **kwargs,
) -> dict:
    """Add a context source (dispatcher for loader/mcp).

    Args:
        name: Internal name
        source_type: Either "loader" or "mcp"
        **kwargs: Type-specific arguments

    Returns:
        The new source config dict
    """
    if source_type == "loader":
        return add_loader_source(name, **kwargs)
    elif source_type == "mcp":
        return add_mcp_source(name, **kwargs)
    else:
        raise ValueError(f"Unknown source type: {source_type}")


def add_pairing(
    name: str,
    display_name: str | None = None,
    search_based: bool = False,
    icon: str = "",
    prompt_hint: str = "",
    enabled: bool = True,
) -> dict:
    """Add a new pairing type to settings.

    Pairings are contextual bonus content (music, food, exercises, tips)
    that complement discovery recommendations.

    Args:
        name: Internal name (e.g., "music", "exercise")
        display_name: User-facing name (e.g., "Listen", "Move")
        search_based: True to use WebSearch, False to generate from knowledge
        icon: Emoji icon for display (e.g., "🎵")
        prompt_hint: Guidance for generating this pairing type
        enabled: Whether to enable immediately

    Returns:
        The new pairing config dict
    """
    if display_name is None:
        display_name = name.replace("_", " ").title()

    settings = load_user_settings()
    if "pairings" not in settings:
        settings["pairings"] = {}

    # Build pairing config
    new_pairing = {
        "display_name": display_name,
        "enabled": enabled,
        "search_based": search_based,
    }
    if icon:
        new_pairing["icon"] = icon
    if prompt_hint:
        new_pairing["prompt_hint"] = prompt_hint
    else:
        # Default prompt hint based on whether it's search-based
        if search_based:
            new_pairing["prompt_hint"] = f"Suggest a {name} that complements the user's context. Search for real links."
        else:
            new_pairing["prompt_hint"] = f"Suggest a {name} that complements the user's context."

    settings["pairings"][name] = new_pairing
    save_user_settings(settings)
    return new_pairing
