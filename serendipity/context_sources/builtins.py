"""Built-in loader functions for common context sources.

These loaders are used by default in types.yaml:
- file_loader: Reads a markdown file
- history_loader: Builds history context
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
    """Build history context with recent items and unextracted ratings.

    Options:
        max_recent: Maximum recent items to include (default: 20)
        include_unextracted: Include unextracted rated items (default: True)
        warn_threshold: Word count warning threshold (default: 10000)

    Returns:
        (content, warnings)
    """
    warnings = []
    max_recent = options.get("max_recent", 20)
    include_unextracted = options.get("include_unextracted", True)
    warn_threshold = options.get("warn_threshold", 10000)

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
            rating_str = f", rating={e.rating}" if e.rating else ", unrated"
            recent_lines.append(f"- {e.url} ({e.type}{rating_str})")
        parts.append(
            "Recently shown (do not repeat these URLs):\n" + "\n".join(recent_lines)
        )

    # Unextracted entries with intensity-aware groupings
    if include_unextracted:
        # Loved items (5/5) - strong positive signal
        loved = storage.get_unextracted_entries(min_rating=5, max_rating=5)
        if loved:
            loved_lines = [f'- {e.url} - "{e.reason[:100]}..."' for e in loved]
            parts.append(
                "Items you LOVED (5/5 - strong positive signal):\n"
                + "\n".join(loved_lines)
            )

        # Liked items (4/5)
        liked = storage.get_unextracted_entries(min_rating=4, max_rating=4)
        if liked:
            liked_lines = [f"- {e.url}" for e in liked]
            parts.append("Items you liked (4/5):\n" + "\n".join(liked_lines))

        # Neutral items (3/5) - not much signal
        neutral = storage.get_unextracted_entries(min_rating=3, max_rating=3)
        if neutral:
            neutral_lines = [f"- {e.url}" for e in neutral]
            parts.append("Items you were neutral about (3/5):\n" + "\n".join(neutral_lines))

        # Disliked items (1-2/5) - avoid similar
        disliked = storage.get_unextracted_entries(max_rating=2)
        if disliked:
            disliked_lines = [f"- {e.url}" for e in disliked]
            parts.append(
                "Items you didn't like (1-2/5 - avoid similar):\n"
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
