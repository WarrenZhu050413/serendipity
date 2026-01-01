"""Configuration types for serendipity recommendation system.

Defines the two-dimensional config schema:
- Approaches: How to find recommendations (convergent, divergent, etc.)
- Media: What format of content (youtube, book, article, etc.)

Simple by default: just enable/disable what you want.
The agent reads your taste.md and decides the distribution.

Supports template variables in config values:
- {profile_dir}: Current profile directory path
- {profile_name}: Current profile name
- {home}: User's home directory
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


def expand_variables(value: Any, context: dict[str, str]) -> Any:
    """Expand template variables in a config value.

    Args:
        value: The value to expand (string, dict, list, or other)
        context: Variable context dict, e.g. {"profile_dir": "/path/to/profile"}

    Returns:
        Value with {variable} placeholders replaced
    """
    if isinstance(value, str):
        # Replace {variable} patterns
        def replace(match):
            var_name = match.group(1)
            return context.get(var_name, match.group(0))
        return re.sub(r"\{(\w+)\}", replace, value)
    elif isinstance(value, dict):
        return {k: expand_variables(v, context) for k, v in value.items()}
    elif isinstance(value, list):
        return [expand_variables(item, context) for item in value]
    else:
        return value


def build_variable_context(
    profile_dir: Optional[Path] = None,
    profile_name: Optional[str] = None,
) -> dict[str, str]:
    """Build the variable context for template expansion.

    Args:
        profile_dir: Path to the profile directory
        profile_name: Name of the profile

    Returns:
        Context dict with available variables
    """
    context = {
        "home": str(Path.home()),
    }
    if profile_dir:
        context["profile_dir"] = str(profile_dir)
    if profile_name:
        context["profile_name"] = profile_name
    return context


def context_from_storage(storage: "StorageManager") -> dict[str, str]:
    """Build variable context from a StorageManager instance.

    Args:
        storage: StorageManager to extract context from

    Returns:
        Context dict for template expansion
    """
    return build_variable_context(
        profile_dir=storage.base_dir,
        profile_name=storage.profile_name,
    )


# Import for type hints only to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from serendipity.storage import StorageManager


@dataclass
class Source:
    """A data source for finding recommendations."""
    tool: str  # WebSearch, WebFetch, mcp__server__tool
    hints: str = ""  # Usage guidance, search patterns, tips


@dataclass
class MetadataField:
    """Schema for a metadata field."""
    name: str
    required: bool = False


@dataclass
class ApproachType:
    """An approach type for finding recommendations."""
    name: str
    display_name: str
    enabled: bool = True
    prompt_hint: str = ""

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ApproachType":
        return cls(
            name=name,
            display_name=data.get("display_name", name.title()),
            enabled=data.get("enabled", True),
            prompt_hint=data.get("prompt_hint", ""),
        )


@dataclass
class PairingType:
    """A pairing type for contextual bonus content.

    Pairings are complementary suggestions (music, food, exercises, tips)
    that enhance the mood of discoveries.
    """
    name: str
    display_name: str
    enabled: bool = True
    search_based: bool = False  # True = use WebSearch, False = generate from knowledge
    icon: str = ""  # Emoji icon for display
    prompt_hint: str = ""
    max_count: Optional[int] = None  # Max instances of this pairing type (None=unlimited)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "PairingType":
        return cls(
            name=name,
            display_name=data.get("display_name", name.title()),
            enabled=data.get("enabled", True),
            search_based=data.get("search_based", False),
            icon=data.get("icon", ""),
            prompt_hint=data.get("prompt_hint", ""),
            max_count=data.get("max_count"),
        )


@dataclass
class MediaType:
    """A media type for recommendations."""
    name: str
    display_name: str
    enabled: bool = True
    preference: str = ""  # Natural language hint to nudge the agent
    sources: list[Source] = field(default_factory=list)
    prompt_hint: str = ""
    metadata_schema: list[MetadataField] = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "MediaType":
        sources = []
        for s in data.get("sources", []):
            sources.append(Source(
                tool=s.get("tool", "WebSearch"),
                hints=s.get("hints", ""),
            ))

        metadata_schema = []
        for m in data.get("metadata_schema", []):
            metadata_schema.append(MetadataField(
                name=m.get("name", ""),
                required=m.get("required", False),
            ))

        return cls(
            name=name,
            display_name=data.get("display_name", name.title()),
            enabled=data.get("enabled", True),
            preference=data.get("preference", ""),
            sources=sources,
            prompt_hint=data.get("prompt_hint", ""),
            metadata_schema=metadata_schema,
        )


@dataclass
class ContextSourceConfig:
    """Configuration for a context source.

    Context sources provide user context through:
    - loader: Python function that returns content to inject into prompt
    - mcp: MCP server providing tools for Claude to search
    """
    name: str
    type: str  # "loader" or "mcp"
    enabled: bool = True
    description: str = ""
    prompt_hint: str = "{content}"
    raw_config: dict = field(default_factory=dict)  # Full config for source implementation

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ContextSourceConfig":
        return cls(
            name=name,
            type=data.get("type", "loader"),
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
            prompt_hint=data.get("prompt_hint", "{content}"),
            raw_config=data,
        )


@dataclass
class DestinationConfig:
    """Configuration for an output destination.

    Output destinations define where to send formatted recommendations:
    - builtin: browser, stdout, file (handled internally)
    - command: Shell out to external CLI tool
    - webhook: HTTP POST to webhook URL
    """
    name: str
    type: str  # "builtin", "command", or "webhook"
    enabled: bool = True
    description: str = ""
    format: Optional[str] = None  # Override format for this destination
    command: Optional[str] = None  # For command type
    webhook_url: Optional[str] = None  # For webhook type
    options: dict = field(default_factory=dict)  # Destination-specific options

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "DestinationConfig":
        return cls(
            name=name,
            type=data.get("type", "builtin"),
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
            format=data.get("format"),
            command=data.get("command"),
            webhook_url=data.get("webhook_url"),
            options=data.get("options", {}),
        )


@dataclass
class OutputConfig:
    """Configuration for output format and destinations.

    Separates format (how to render) from destination (where to send):
    - default_format: json, markdown, html
    - default_destination: browser, stdout, file, gmail, slack, etc.
    - destinations: Dict of configured destination plugins
    """
    default_format: str = "html"
    default_destination: str = "browser"
    destinations: dict[str, DestinationConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "OutputConfig":
        destinations = {}
        for name, d_data in data.get("destinations", {}).items():
            destinations[name] = DestinationConfig.from_dict(name, d_data)

        return cls(
            default_format=data.get("default_format", "html"),
            default_destination=data.get("default_destination", "browser"),
            destinations=destinations,
        )

    @classmethod
    def default(cls) -> "OutputConfig":
        """Return default output config with browser destination."""
        return cls(
            default_format="html",
            default_destination="browser",
            destinations={
                "browser": DestinationConfig(
                    name="browser",
                    type="builtin",
                    enabled=True,
                    description="Open in browser with interactive UI",
                ),
                "stdout": DestinationConfig(
                    name="stdout",
                    type="builtin",
                    enabled=True,
                    description="Print to terminal",
                ),
                "file": DestinationConfig(
                    name="file",
                    type="builtin",
                    enabled=True,
                    description="Save to file only",
                ),
            },
        )

    def get_destination(self, name: str) -> Optional[DestinationConfig]:
        """Get a destination by name."""
        return self.destinations.get(name)

    def get_enabled_destinations(self) -> list[DestinationConfig]:
        """Get list of enabled destinations."""
        return [d for d in self.destinations.values() if d.enabled]


@dataclass
class TypesConfig:
    """Serendipity settings - single source of truth.

    All configuration in one file (~/.serendipity/settings.yaml):
    - model, total_count, feedback_server_port: Runtime settings
    - approaches: How to find (convergent, divergent)
    - media: What format (article, youtube, book, podcast)
    - context_sources: Where to get user profile/preferences
    - output: Format and destination for recommendations
    - pairings: Contextual bonus content (music, food, exercises, tips)

    Simple by default: just enable/disable what you want.
    The agent reads your taste.md and decides the distribution.
    """
    version: int = 2
    model: str = "opus"
    total_count: int = 10
    feedback_server_port: int = 9876
    thinking_tokens: Optional[int] = None  # Extended thinking budget (None=disabled)
    approaches: dict[str, ApproachType] = field(default_factory=dict)
    media: dict[str, MediaType] = field(default_factory=dict)
    context_sources: dict[str, ContextSourceConfig] = field(default_factory=dict)
    output: OutputConfig = field(default_factory=OutputConfig.default)
    pairings: dict[str, PairingType] = field(default_factory=dict)
    pairings_enabled: bool = True  # Master toggle for pairings system

    @classmethod
    def from_dict(cls, data: dict) -> "TypesConfig":
        """Create from dictionary (parsed YAML)."""
        approaches = {}
        for name, a_data in data.get("approaches", {}).items():
            approaches[name] = ApproachType.from_dict(name, a_data)

        media = {}
        for name, m_data in data.get("media", {}).items():
            media[name] = MediaType.from_dict(name, m_data)

        context_sources = {}
        for name, cs_data in data.get("context_sources", {}).items():
            context_sources[name] = ContextSourceConfig.from_dict(name, cs_data)

        # Parse output config, with defaults if not specified
        output_data = data.get("output", {})
        output = OutputConfig.from_dict(output_data) if output_data else OutputConfig.default()

        # Parse pairings config
        pairings = {}
        for name, p_data in data.get("pairings", {}).items():
            pairings[name] = PairingType.from_dict(name, p_data)

        return cls(
            version=data.get("version", 2),
            model=data.get("model", "opus"),
            total_count=data.get("total_count", 10),
            feedback_server_port=data.get("feedback_server_port", 9876),
            thinking_tokens=data.get("thinking_tokens"),  # None if not set
            approaches=approaches,
            media=media,
            context_sources=context_sources,
            output=output,
            pairings=pairings,
            pairings_enabled=data.get("pairings_enabled", True),
        )

    @classmethod
    def from_yaml(
        cls,
        path: Path,
        variable_context: Optional[dict[str, str]] = None,
    ) -> "TypesConfig":
        """Load from YAML file, creating from defaults if missing.

        Args:
            path: Path to settings.yaml
            variable_context: Optional dict for template variable expansion.
                              Keys like "profile_dir", "profile_name", "home".

        Returns:
            Loaded configuration with variables expanded
        """
        if not path.exists():
            cls.write_defaults(path)
        content = path.read_text()
        data = yaml.safe_load(content) or {}

        # Expand template variables if context provided
        if variable_context:
            data = expand_variables(data, variable_context)

        return cls.from_dict(data)

    @classmethod
    def default(cls) -> "TypesConfig":
        """Load default configuration from package resource.

        Single source of truth: serendipity/config/defaults/settings.yaml
        """
        from serendipity.resources import get_default_settings_yaml
        content = get_default_settings_yaml()
        data = yaml.safe_load(content) or {}
        return cls.from_dict(data)

    @classmethod
    def write_defaults(cls, path: Path) -> None:
        """Write default settings.yaml to the given path.

        Copies the package default to user's config directory.
        """
        from serendipity.resources import get_default_settings_yaml
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(get_default_settings_yaml())

    @classmethod
    def reset(cls, path: Path) -> None:
        """Reset settings.yaml to defaults (overwrites existing)."""
        cls.write_defaults(path)

    def get_enabled_approaches(self) -> list[ApproachType]:
        """Get list of enabled approach types."""
        return [a for a in self.approaches.values() if a.enabled]

    def get_enabled_media(self) -> list[MediaType]:
        """Get list of enabled media types."""
        return [m for m in self.media.values() if m.enabled]

    def get_enabled_pairings(self) -> list[PairingType]:
        """Get list of enabled pairing types.

        Returns empty list if pairings_enabled is False (master toggle).
        """
        if not self.pairings_enabled:
            return []
        return [p for p in self.pairings.values() if p.enabled]
