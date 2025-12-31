"""Built-in loader functions for common context sources.

These loaders are used by default in types.yaml:
- file_loader: Reads a markdown file
- history_loader: Builds history context
- style_loader: Returns HTML styling guidance
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from serendipity.storage import StorageManager


def file_loader(storage: "StorageManager", options: dict) -> tuple[str, list[str]]:
    """Load content from a file.

    Options:
        path: File path (supports ~ expansion)
        warn_threshold: Word count warning threshold (optional)

    Returns:
        (content, warnings)
    """
    warnings = []
    path_str = options.get("path", "")
    if not path_str:
        return "", [f"No path specified in file_loader options"]

    path = Path(path_str).expanduser()
    if not path.exists():
        return "", []  # Missing file is OK, just empty

    content = path.read_text()

    # Check word count if threshold specified
    warn_threshold = options.get("warn_threshold")
    if warn_threshold:
        word_count = len(content.split())
        if word_count > warn_threshold:
            warnings.append(
                f"File {path.name} is {word_count:,} words (>{warn_threshold:,})"
            )

    return content, warnings


def history_loader(storage: "StorageManager", options: dict) -> tuple[str, list[str]]:
    """Build history context with recent items and unextracted feedback.

    Options:
        max_recent: Maximum recent items to include (default: 20)
        include_unextracted: Include unextracted likes/dislikes (default: True)
        warn_threshold: Word count warning threshold (default: 10000)

    Returns:
        (content, warnings)
    """
    warnings = []
    max_recent = options.get("max_recent", 20)
    include_unextracted = options.get("include_unextracted", True)
    warn_threshold = options.get("warn_threshold", 10000)

    config = storage.load_config()
    if not config.history_enabled:
        return "", []

    parts = []

    # Learnings (extracted patterns)
    learnings = storage.load_learnings()
    if learnings.strip():
        parts.append(f"<discovery_learnings>\n{learnings}\n</discovery_learnings>")

    # Recent entries (to avoid repeating)
    recent = storage.load_recent_history(max_recent)
    if recent:
        recent_lines = []
        for e in recent:
            feedback_str = f", {e.feedback}" if e.feedback else ", no feedback"
            recent_lines.append(f"- {e.url} ({e.type}{feedback_str})")
        parts.append(
            "Recently shown (do not repeat these URLs):\n" + "\n".join(recent_lines)
        )

    # Unextracted liked/disliked entries
    if include_unextracted:
        unextracted_liked = storage.get_unextracted_entries("liked")
        if unextracted_liked:
            liked_lines = [
                f'- {e.url} - "{e.reason[:100]}..."' for e in unextracted_liked
            ]
            parts.append(
                "Items you've liked (not yet in learnings):\n" + "\n".join(liked_lines)
            )

        unextracted_disliked = storage.get_unextracted_entries("disliked")
        if unextracted_disliked:
            disliked_lines = [f"- {e.url}" for e in unextracted_disliked]
            parts.append(
                "Items you didn't like (not yet in learnings):\n"
                + "\n".join(disliked_lines)
            )

    if not parts:
        return "", []

    content = "\n\n".join(parts)

    # Check word count
    word_count = len(content.split())
    if word_count > warn_threshold:
        warnings.append(
            f"History context is {word_count:,} words (>{warn_threshold:,}). "
            f"Consider extracting learnings with 'serendipity profile learnings -i'"
        )

    return content, warnings


def style_loader(storage: "StorageManager", options: dict) -> tuple[str, list[str]]:
    """Load HTML styling guidance from config.

    Returns:
        (content, warnings)
    """
    config = storage.load_config()
    if config.html_style:
        content = f"Style the HTML output as: {config.html_style}"
    else:
        content = (
            "Generate HTML styling that reflects the user's aesthetic taste "
            "based on their preferences and the nature of the recommendations."
        )
    return content, []
