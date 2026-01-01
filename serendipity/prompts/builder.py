"""Dynamic prompt builder for serendipity recommendations.

Compiles TypesConfig into prompt sections with:
- Approach descriptions
- Media type descriptions with search patterns
- Agent guidance (you choose the distribution)
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

PAIRING_ICONS = {
    "music": "🎵",
    "exercise": "🏃",
    "food": "🍽️",
    "tip": "💡",
    "quote": "📜",
    "action": "🎯",
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

            # Add search sources (default to WebSearch if none specified)
            sources = media.sources if media.sources else []
            if not sources:
                # Default search hint when no sources configured
                lines.append("")
                lines.append("**Search hints:**")
                lines.append(f"- WebSearch: {media.name} {{query}}")
            else:
                lines.append("")
                lines.append("**Search hints:**")
                for source in sources:
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

    def build_distribution_guidance(self) -> str:
        """Generate simple guidance for the agent to choose distribution."""
        media_types = self.config.get_enabled_media()

        lines = ["## DISTRIBUTION", ""]
        lines.append(f"**Total: {self.config.total_count} recommendations**")
        lines.append("")
        lines.append("You choose the distribution based on the user's taste.md and context.")
        lines.append("Balance between approaches and media types as you see fit.")
        lines.append("")

        # Show any preference hints
        prefs = [(m.display_name, m.preference) for m in media_types if m.preference]
        if prefs:
            lines.append("**User preferences:**")
            for name, pref in prefs:
                lines.append(f"- {name}: {pref}")
            lines.append("")

        return "\n".join(lines)

    def build_pairings_section(self) -> str:
        """Generate markdown for pairing types (bonus contextual content)."""
        enabled_pairings = self.config.get_enabled_pairings()

        if not enabled_pairings:
            return ""

        lines = ["## PAIRINGS (bonus contextual content)", ""]
        lines.append("In addition to recommendations, include 3-4 pairings that complement the user's context.")
        lines.append("Like wine pairings for food - these enhance the discovery experience.")
        lines.append("")

        # Check for max_count constraints
        constraints = [(p.display_name, p.max_count) for p in enabled_pairings if p.max_count is not None]
        if constraints:
            lines.append("**Constraints:**")
            for name, max_count in constraints:
                lines.append(f"- {name}: maximum {max_count}")
            lines.append("")

        # Separate search-based and generated pairings
        search_based = [p for p in enabled_pairings if p.search_based]
        generated = [p for p in enabled_pairings if not p.search_based]

        if search_based:
            lines.append("### Search-Based Pairings (use WebSearch)")
            for pairing in search_based:
                icon = pairing.icon or PAIRING_ICONS.get(pairing.name, "✨")
                max_note = f" (max {pairing.max_count})" if pairing.max_count else ""
                lines.append(f"#### {icon} {pairing.display_name}{max_note}")
                if pairing.prompt_hint:
                    lines.append(pairing.prompt_hint.strip())
                lines.append("")

        if generated:
            lines.append("### Generated Pairings (from your knowledge)")
            for pairing in generated:
                icon = pairing.icon or PAIRING_ICONS.get(pairing.name, "✨")
                max_note = f" (max {pairing.max_count})" if pairing.max_count else ""
                lines.append(f"#### {icon} {pairing.display_name}{max_note}")
                if pairing.prompt_hint:
                    lines.append(pairing.prompt_hint.strip())
                lines.append("")

        lines.append("Choose 3-4 pairings that best fit the user's current context. Quality over quantity.")
        lines.append("")

        return "\n".join(lines)

    def build_output_schema(self) -> str:
        """Generate the expected output JSON schema."""
        approaches = [a.name for a in self.config.get_enabled_approaches()]
        media_types = [m.name for m in self.config.get_enabled_media()]
        enabled_pairings = self.config.get_enabled_pairings()

        lines = ["## OUTPUT FORMAT", ""]
        lines.append("Wrap your output JSON in <recommendations> tags:")
        lines.append("")
        lines.append("<recommendations>")
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
            # Always add comma if pairings follow, else check if more approaches
            if enabled_pairings or i < len(approaches) - 1:
                lines.append('  ],')
            else:
                lines.append('  ]')

        # Add pairings section if enabled
        if enabled_pairings:
            pairing_types = [p.name for p in enabled_pairings]
            lines.append('  "pairings": [')
            lines.append('    {')
            lines.append(f'      "type": "{pairing_types[0] if pairing_types else "tip"}",')
            lines.append('      "content": "The pairing suggestion/description",')
            lines.append('      "url": "Optional: link for search-based pairings",')
            lines.append('      "title": "Optional: title for the pairing"')
            lines.append('    }')
            lines.append('  ]')

        lines.append("}")
        lines.append("```")
        lines.append("</recommendations>")
        return "\n".join(lines)

    def build_type_guidance(self) -> str:
        """Build the type guidance section (approaches, media, distribution, pairings)."""
        sections = [
            self.build_approach_section(),
            self.build_media_section(),
            self.build_distribution_guidance(),
            self.build_pairings_section(),
        ]
        # Filter out empty sections (e.g., pairings when disabled)
        return "\n\n".join(s for s in sections if s)
