"""Storage manager for serendipity history and preferences.

Configuration is now in settings.yaml (via TypesConfig).
This module handles history.jsonl, learnings.md, and output files.
"""

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class HistoryEntry:
    """A single history entry with extended metadata.

    Supports both simple format (backwards compatible) and extended format
    with media type, title, thumbnail, and type-specific metadata.
    """

    url: str
    reason: str
    type: str  # approach: "convergent" or "divergent"
    feedback: Optional[str]  # None, "liked", or "disliked"
    timestamp: str
    session_id: str
    extracted: bool = False  # True if this item has been extracted into a rule

    # Extended fields (optional for backwards compatibility)
    media_type: str = "article"  # youtube, book, article, podcast, etc.
    title: Optional[str] = None
    thumbnail_url: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "url": self.url,
            "reason": self.reason,
            "type": self.type,
            "feedback": self.feedback,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "extracted": self.extracted,
        }
        # Only include extended fields if they have values
        if self.media_type != "article":
            result["media_type"] = self.media_type
        if self.title:
            result["title"] = self.title
        if self.thumbnail_url:
            result["thumbnail_url"] = self.thumbnail_url
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        """Create from dictionary, handling both simple and extended formats."""
        return cls(
            url=data.get("url", ""),
            reason=data.get("reason", ""),
            type=data.get("type", ""),
            feedback=data.get("feedback"),
            timestamp=data.get("timestamp", ""),
            session_id=data.get("session_id", ""),
            extracted=data.get("extracted", False),
            media_type=data.get("media_type", "article"),
            title=data.get("title"),
            thumbnail_url=data.get("thumbnail_url"),
            metadata=data.get("metadata", {}),
        )


class StorageManager:
    """Manages serendipity storage: history, learnings, and output files.

    Note: Configuration is now handled by TypesConfig in settings.yaml.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize storage manager.

        Args:
            base_dir: Base directory for storage. Defaults to ~/.serendipity
        """
        self.base_dir = base_dir or Path.home() / ".serendipity"

    @property
    def settings_path(self) -> Path:
        return self.base_dir / "settings.yaml"

    @property
    def history_path(self) -> Path:
        return self.base_dir / "history.jsonl"

    @property
    def learnings_path(self) -> Path:
        return self.base_dir / "learnings.md"

    @property
    def taste_path(self) -> Path:
        return self.base_dir / "taste.md"

    @property
    def template_path(self) -> Path:
        return self.base_dir / "template.html"

    @property
    def output_dir(self) -> Path:
        return self.base_dir / "output"

    def get_template_path(self, default_content: str) -> Path:
        """Get template path, writing default content on first use.

        Args:
            default_content: Default template content to write if user template doesn't exist

        Returns:
            Path to the user's template file
        """
        if not self.template_path.exists():
            self.template_path.parent.mkdir(parents=True, exist_ok=True)
            self.template_path.write_text(default_content)

        return self.template_path

    def ensure_dirs(self) -> None:
        """Ensure storage directories exist."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def migrate_if_needed(self) -> list[str]:
        """Migrate old files to new names.

        Returns:
            List of migration messages (empty if no migrations needed).
        """
        migrations = []

        # Migrate preferences.md → taste.md
        old_prefs = self.base_dir / "preferences.md"
        if old_prefs.exists() and not self.taste_path.exists():
            shutil.move(str(old_prefs), str(self.taste_path))
            migrations.append("Migrated preferences.md → taste.md")

        # Migrate rules.md → learnings.md
        old_rules = self.base_dir / "rules.md"
        if old_rules.exists() and not self.learnings_path.exists():
            shutil.move(str(old_rules), str(self.learnings_path))
            migrations.append("Migrated rules.md → learnings.md")

        # Migrate types.yaml → settings.yaml
        old_types = self.base_dir / "types.yaml"
        if old_types.exists() and not self.settings_path.exists():
            shutil.move(str(old_types), str(self.settings_path))
            migrations.append("Migrated types.yaml → settings.yaml")

        # Remove old config.json (settings are now in settings.yaml)
        old_config = self.base_dir / "config.json"
        if old_config.exists():
            old_config.unlink()
            migrations.append("Removed config.json (settings now in settings.yaml)")

        return migrations

    def load_taste(self) -> str:
        """Load user taste profile from file."""
        if not self.taste_path.exists():
            return ""
        return self.taste_path.read_text()

    # Learnings management (extracted patterns from feedback)

    def load_learnings(self) -> str:
        """Load learnings markdown."""
        if not self.learnings_path.exists():
            return ""
        return self.learnings_path.read_text()

    def save_learnings(self, content: str) -> None:
        """Save learnings markdown."""
        self.ensure_dirs()
        self.learnings_path.write_text(content)

    def append_learning(self, title: str, content: str, learning_type: str = "like") -> None:
        """Append a new learning to learnings.md.

        Args:
            title: Learning title (will be ### heading)
            content: Learning content (2-3 sentences)
            learning_type: "like" or "dislike"
        """
        existing = self.load_learnings()

        # Initialize structure if empty
        if not existing.strip():
            existing = "# My Discovery Learnings\n\n## Likes\n\n## Dislikes\n"

        section_header = "## Likes" if learning_type == "like" else "## Dislikes"
        new_learning = f"\n### {title}\n{content}\n"

        # Find the section and append
        if section_header in existing:
            # Find where to insert (after section header, before next section or end)
            section_start = existing.find(section_header)
            section_end = len(existing)

            # Find the next ## section after this one
            next_section = existing.find("\n## ", section_start + len(section_header))
            if next_section != -1:
                section_end = next_section

            # Insert before the next section (or at end)
            updated = existing[:section_end].rstrip() + new_learning + existing[section_end:]
        else:
            # Add the section if it doesn't exist
            updated = existing.rstrip() + f"\n\n{section_header}\n{new_learning}"

        self.save_learnings(updated)

    def clear_learnings(self) -> None:
        """Clear all learnings."""
        if self.learnings_path.exists():
            self.learnings_path.unlink()

    def mark_extracted(self, urls: list[str]) -> int:
        """Mark entries as extracted by URL.

        Args:
            urls: List of URLs to mark as extracted

        Returns:
            Number of entries updated
        """
        if not self.history_path.exists():
            return 0

        entries = self.load_all_history()
        url_set = set(urls)
        updated_count = 0

        for entry in entries:
            if entry.url in url_set and not entry.extracted:
                entry.extracted = True
                updated_count += 1

        if updated_count > 0:
            # Rewrite the file
            self.history_path.unlink()
            self.append_history(entries)

        return updated_count

    def get_unextracted_entries(self, feedback: str = None) -> list[HistoryEntry]:
        """Get entries not yet extracted into rules.

        Args:
            feedback: Optional filter by feedback type ("liked" or "disliked")

        Returns:
            List of unextracted entries
        """
        entries = self.load_all_history()
        return [
            e for e in entries
            if not e.extracted and (feedback is None or e.feedback == feedback)
        ]

    def append_history(self, entries: list[HistoryEntry]) -> None:
        """Append entries to history file."""
        self.ensure_dirs()
        with open(self.history_path, "a") as f:
            for entry in entries:
                f.write(json.dumps(entry.to_dict()) + "\n")

    def load_all_history(self) -> list[HistoryEntry]:
        """Load all history entries."""
        if not self.history_path.exists():
            return []

        entries = []
        with open(self.history_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        entries.append(HistoryEntry.from_dict(data))
                    except json.JSONDecodeError:
                        continue
        return entries

    def load_recent_history(self, limit: int = 20) -> list[HistoryEntry]:
        """Load recent history entries.

        Args:
            limit: Maximum number of entries to return. Defaults to 20.

        Returns:
            List of recent history entries, newest first.
        """
        entries = self.load_all_history()
        # Return most recent entries
        return entries[-limit:] if entries else []

    def update_feedback(self, url: str, session_id: str, feedback: str) -> bool:
        """Update feedback for a specific recommendation.

        Args:
            url: URL of the recommendation
            session_id: Session ID of the recommendation
            feedback: Feedback value ("liked" or "disliked")

        Returns:
            True if entry was found and updated, False otherwise.
        """
        if not self.history_path.exists():
            return False

        entries = self.load_all_history()
        updated = False

        for entry in entries:
            if entry.url == url and entry.session_id == session_id:
                entry.feedback = feedback
                updated = True
                break

        if updated:
            # Rewrite the file
            self.history_path.unlink()
            self.append_history(entries)

        return updated

    def get_liked_entries(self) -> list[HistoryEntry]:
        """Get all liked history entries."""
        return [e for e in self.load_all_history() if e.feedback == "liked"]

    def get_disliked_entries(self) -> list[HistoryEntry]:
        """Get all disliked history entries."""
        return [e for e in self.load_all_history() if e.feedback == "disliked"]

    def clear_history(self) -> None:
        """Clear all history."""
        if self.history_path.exists():
            self.history_path.unlink()

    def count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())

    def build_history_context(self, max_recent: int = 20, warn_callback=None) -> str:
        """Build the history context string for the prompt.

        Args:
            max_recent: Maximum number of recent entries to include.
            warn_callback: Optional callback function to emit warnings.
                           Called with (message: str) when context is too long.

        Returns:
            String with history context (learnings, recent items, unextracted likes/dislikes).
        """
        history_parts = []

        # 1. Discovery learnings (compact, high signal - extracted patterns)
        learnings = self.load_learnings()
        if learnings.strip():
            history_parts.append(f"<discovery_learnings>\n{learnings}\n</discovery_learnings>")

        # 2. Recent entries (to avoid repeating) - include all, extracted or not
        recent = self.load_recent_history(limit=max_recent)
        if recent:
            recent_lines = []
            for e in recent:
                feedback_str = f", {e.feedback}" if e.feedback else ", no feedback"
                recent_lines.append(f"- {e.url} ({e.type}{feedback_str})")
            history_parts.append(
                "Recently shown (do not repeat these URLs):\n" + "\n".join(recent_lines)
            )

        # 3. Unextracted liked entries (not yet in learnings)
        unextracted_liked = self.get_unextracted_entries("liked")
        if unextracted_liked:
            liked_lines = [f"- {e.url} - \"{e.reason[:100]}...\"" for e in unextracted_liked]
            history_parts.append(
                "Items you've liked (not yet in learnings):\n" + "\n".join(liked_lines)
            )

        # 4. Unextracted disliked entries (not yet in learnings)
        unextracted_disliked = self.get_unextracted_entries("disliked")
        if unextracted_disliked:
            disliked_lines = [f"- {e.url}" for e in unextracted_disliked]
            history_parts.append(
                "Items you didn't like (not yet in learnings):\n" + "\n".join(disliked_lines)
            )

        if not history_parts:
            return ""

        result = "<history_context>\n" + "\n\n".join(history_parts) + "\n</history_context>"

        # Check total word count and warn if too long
        word_count = self.count_words(result)
        if word_count > 10000 and warn_callback:
            warn_callback(
                f"History context is {word_count:,} words (>10K). "
                f"Consider extracting learnings with 'serendipity profile learnings -i' "
                f"or clearing old entries with 'serendipity profile history --clear'."
            )

        return result
