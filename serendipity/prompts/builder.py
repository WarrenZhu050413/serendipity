"""Dynamic prompt builder for serendipity recommendations.

Compiles TypesConfig into prompt sections with:
- Approach descriptions
- Media type descriptions with search patterns
- Distribution matrix
- Output JSON schema
"""

from serendipity.config.types import TypesConfig


MEDIA_ICONS = {
    "youtube": "📺",
    "book": "📚",
    "article": "📰",
    "podcast": "🎙️",
    "tool": "🔧",
    "archive": "📜",
    "newsletter": "✉️",
    "repository": "💻",
    "course": "🎓",
    "community": "👥",
    "person": "👤",
    "event": "📅",
    "music": "🎵",
    "image": "🖼️",
}


class PromptBuilder:
    """Builds dynamic prompts from TypesConfig."""

    def __init__(self, config: TypesConfig):
        self.config = config

    def build_approach_section(self) -> str:
        """Generate markdown for approach types."""
        lines = ["## APPROACH TYPES (how to find)", ""]
        for approach in self.config.get_enabled_approaches():
            lines.append(f"### {approach.display_name}")
            lines.append(f"*{approach.description}*")
            if approach.prompt_hint:
                lines.append("")
                lines.append(approach.prompt_hint.strip())
            lines.append("")
        return "\n".join(lines)

    def build_media_section(self) -> str:
        """Generate markdown for media types with search patterns."""
        lines = ["## MEDIA TYPES (what format)", ""]
        for media in self.config.get_enabled_media():
            icon = MEDIA_ICONS.get(media.name, "📄")
            lines.append(f"### {icon} {media.display_name}")
            lines.append(f"*{media.description}*")

            # Add search sources
            if media.sources:
                lines.append("")
                lines.append("**Search hints:**")
                for source in media.sources:
                    lines.append(f"- {source.tool}: {source.hints.strip()}")

            # Add prompt hint
            if media.prompt_hint:
                lines.append("")
                lines.append(media.prompt_hint.strip())

            # Add required metadata
            required = [f.name for f in media.metadata_schema if f.required]
            if required:
                lines.append("")
                lines.append(f"**Required metadata:** {', '.join(required)}")

            lines.append("")
        return "\n".join(lines)

    def build_distribution_table(self) -> str:
        """Generate distribution guidance table."""
        matrix = self.config.calculate_distribution()
        approaches = list(matrix.keys())
        media_types = list(self.config.get_enabled_media())

        lines = ["## RECOMMENDED DISTRIBUTION", ""]

        if self.config.agent_mode == "autonomous":
            lines.append("*Use your judgment to adjust based on context quality.*")
        else:
            lines.append("*Follow these counts strictly.*")
        lines.append("")

        # Build markdown table
        header = "| Approach | " + " | ".join(m.display_name for m in media_types) + " |"
        separator = "|----------|" + "|".join("-" * len(m.display_name) for m in media_types) + "|"

        lines.append(header)
        lines.append(separator)

        for approach_name in approaches:
            row = f"| {approach_name.title()} |"
            for media in media_types:
                count = matrix.get(approach_name, {}).get(media.name, 0)
                row += f" ~{count:.0f} |"
            lines.append(row)

        lines.append("")
        lines.append(f"**Total: {self.config.total_count} recommendations**")
        return "\n".join(lines)

    def build_output_schema(self) -> str:
        """Generate the expected output JSON schema."""
        approaches = [a.name for a in self.config.get_enabled_approaches()]
        media_types = [m.name for m in self.config.get_enabled_media()]

        lines = ["## OUTPUT FORMAT", ""]
        lines.append("Structure your recommendations as:")
        lines.append("")
        lines.append("```json")
        lines.append("{")

        for i, approach in enumerate(approaches):
            lines.append(f'  "{approach}": [')
            lines.append('    {')
            lines.append('      "url": "https://...",')
            lines.append('      "reason": "Brief reason (1-2 sentences)",')
            lines.append(f'      "type": "{media_types[0] if media_types else "article"}",')
            lines.append('      "title": "Optional title",')
            lines.append('      "thumbnail_url": "Optional image URL",')
            lines.append('      "metadata": {"key": "value"}')
            lines.append('    }')
            if i < len(approaches) - 1:
                lines.append('  ],')
            else:
                lines.append('  ]')

        lines.append("}")
        lines.append("```")
        return "\n".join(lines)

    def build_type_guidance(self) -> str:
        """Build the complete type guidance section for the prompt."""
        sections = [
            self.build_approach_section(),
            self.build_media_section(),
            self.build_distribution_table(),
            self.build_output_schema(),
        ]
        return "\n\n".join(sections)
