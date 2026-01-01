"""Icon handling for serendipity pairings.

Icons are auto-discovered from static/icons/*.svg.
Single source of truth: just drop an SVG file in the folder.
"""

from pathlib import Path
from functools import lru_cache
import json
import re

ICONS_DIR = Path(__file__).parent / "static" / "icons"


@lru_cache(maxsize=1)
def discover_icons() -> dict[str, str]:
    """Auto-discover SVGs and return {name: svg_content}."""
    icons = {}
    if ICONS_DIR.exists():
        for svg_path in ICONS_DIR.glob("*.svg"):
            name = svg_path.stem  # "music.svg" -> "music"
            icons[name] = svg_path.read_text()
    return icons


def get_icon_html(name: str, css_class: str = "pairing-icon-svg") -> str:
    """Get inline SVG HTML for an icon."""
    icons = discover_icons()
    svg = icons.get(name)
    if svg:
        return svg.replace("<svg", f'<svg class="{css_class}"', 1)
    return f'<span class="{css_class}">&#10024;</span>'  # sparkles fallback


def get_icon_terminal(name: str) -> str:
    """Get terminal-safe fallback."""
    return "•" if name in discover_icons() else "✨"


def get_icons_json() -> str:
    """Get all icons as JSON for template injection.

    Extracts inner SVG content (paths, circles, etc.) for lightweight JS usage.
    """
    icons = discover_icons()
    paths = {}
    for name, svg in icons.items():
        # Extract content between <svg> tags
        match = re.search(r'<svg[^>]*>(.*)</svg>', svg, re.DOTALL)
        paths[name] = match.group(1).strip() if match else ""
    return json.dumps(paths)
