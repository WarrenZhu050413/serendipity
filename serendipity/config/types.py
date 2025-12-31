"""Configuration types for serendipity recommendation system.

Defines the two-dimensional config schema:
- Approaches: How to find recommendations (convergent, divergent, etc.)
- Media: What format of content (youtube, book, article, etc.)

A recommendation is always {approach} × {media}.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


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
    description: str
    enabled: bool = True
    weight: float = 0.5
    count: Optional[int] = None  # Hard limit (overrides weight)
    prompt_hint: str = ""

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ApproachType":
        return cls(
            name=name,
            display_name=data.get("display_name", name.title()),
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            weight=data.get("weight", 0.5),
            count=data.get("count"),
            prompt_hint=data.get("prompt_hint", ""),
        )


@dataclass
class MediaType:
    """A media type for recommendations."""
    name: str
    display_name: str
    description: str
    enabled: bool = True
    weight: float = 0.2
    count: Optional[int] = None  # Hard limit (overrides weight)
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
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            weight=data.get("weight", 0.2),
            count=data.get("count"),
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
class TypesConfig:
    """Configuration for recommendation types.

    Two orthogonal dimensions:
    - approaches: How to find (convergent, divergent, etc.)
    - media: What format (youtube, book, article, etc.)

    Plus context sources for user context:
    - context_sources: Where to get user profile/preferences
    """
    version: int = 1
    approaches: dict[str, ApproachType] = field(default_factory=dict)
    media: dict[str, MediaType] = field(default_factory=dict)
    context_sources: dict[str, ContextSourceConfig] = field(default_factory=dict)
    overrides: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    total_count: int = 10
    agent_mode: str = "autonomous"  # "autonomous" or "strict"

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

        return cls(
            version=data.get("version", 1),
            approaches=approaches,
            media=media,
            context_sources=context_sources,
            overrides=data.get("overrides", {}),
            total_count=data.get("total_count", 10),
            agent_mode=data.get("agent_mode", "autonomous"),
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "TypesConfig":
        """Load from YAML file, creating from defaults if missing."""
        if not path.exists():
            cls.write_defaults(path)
        content = path.read_text()
        data = yaml.safe_load(content) or {}
        return cls.from_dict(data)

    @classmethod
    def default(cls) -> "TypesConfig":
        """Load default configuration from package resource.

        Single source of truth: serendipity/config/defaults/types.yaml
        """
        from serendipity.resources import get_default_types_yaml
        content = get_default_types_yaml()
        data = yaml.safe_load(content) or {}
        return cls.from_dict(data)

    @classmethod
    def write_defaults(cls, path: Path) -> None:
        """Write default types.yaml to the given path.

        Copies the package default to user's config directory.
        """
        from serendipity.resources import get_default_types_yaml
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(get_default_types_yaml())

    @classmethod
    def reset(cls, path: Path) -> None:
        """Reset types.yaml to defaults (overwrites existing)."""
        cls.write_defaults(path)

    def get_enabled_approaches(self) -> list[ApproachType]:
        """Get list of enabled approach types."""
        return [a for a in self.approaches.values() if a.enabled]

    def get_enabled_media(self) -> list[MediaType]:
        """Get list of enabled media types."""
        return [m for m in self.media.values() if m.enabled]

    def calculate_distribution(self) -> dict[str, dict[str, float]]:
        """Calculate approach × media → count distribution matrix.

        Returns:
            Nested dict: {approach_name: {media_name: expected_count}}
        """
        matrix = {}
        total = self.total_count

        for approach in self.get_enabled_approaches():
            matrix[approach.name] = {}

            for media in self.get_enabled_media():
                # Check for override
                override = self.overrides.get(approach.name, {}).get(media.name, {})
                if "weight" in override:
                    weight = override["weight"]
                else:
                    weight = approach.weight * media.weight

                matrix[approach.name][media.name] = round(weight * total, 1)

        return matrix
