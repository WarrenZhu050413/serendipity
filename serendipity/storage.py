"""Storage manager for serendipity configuration, history, and preferences."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class Config:
    """Serendipity configuration."""

    preferences_path: str = "~/.serendipity/preferences.md"
    history_enabled: bool = True
    max_recent_history: int = 20
    summarize_old_history: bool = True
    summary_threshold: int = 50
    feedback_server_port: int = 9876
    default_model: str = "opus"
    default_n1: int = 5
    default_n2: int = 5
    html_style: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "preferences_path": self.preferences_path,
            "history_enabled": self.history_enabled,
            "max_recent_history": self.max_recent_history,
            "summarize_old_history": self.summarize_old_history,
            "summary_threshold": self.summary_threshold,
            "feedback_server_port": self.feedback_server_port,
            "default_model": self.default_model,
            "default_n1": self.default_n1,
            "default_n2": self.default_n2,
            "html_style": self.html_style,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """Create from dictionary."""
        return cls(
            preferences_path=data.get("preferences_path", "~/.serendipity/preferences.md"),
            history_enabled=data.get("history_enabled", True),
            max_recent_history=data.get("max_recent_history", 20),
            summarize_old_history=data.get("summarize_old_history", True),
            summary_threshold=data.get("summary_threshold", 50),
            feedback_server_port=data.get("feedback_server_port", 9876),
            default_model=data.get("default_model", "opus"),
            default_n1=data.get("default_n1", 5),
            default_n2=data.get("default_n2", 5),
            html_style=data.get("html_style"),
        )


@dataclass
class HistoryEntry:
    """A single history entry."""

    url: str
    reason: str
    type: str  # "convergent" or "divergent"
    feedback: Optional[str]  # None, "liked", or "disliked"
    timestamp: str
    session_id: str
    extracted: bool = False  # True if this item has been extracted into a rule

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "url": self.url,
            "reason": self.reason,
            "type": self.type,
            "feedback": self.feedback,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "extracted": self.extracted,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        """Create from dictionary."""
        return cls(
            url=data.get("url", ""),
            reason=data.get("reason", ""),
            type=data.get("type", ""),
            feedback=data.get("feedback"),
            timestamp=data.get("timestamp", ""),
            session_id=data.get("session_id", ""),
            extracted=data.get("extracted", False),
        )


class StorageManager:
    """Manages serendipity storage: config, history, and preferences."""

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize storage manager.

        Args:
            base_dir: Base directory for storage. Defaults to ~/.serendipity
        """
        self.base_dir = base_dir or Path.home() / ".serendipity"
        self._config: Optional[Config] = None

    @property
    def config_path(self) -> Path:
        return self.base_dir / "config.json"

    @property
    def history_path(self) -> Path:
        return self.base_dir / "history.jsonl"

    @property
    def summary_path(self) -> Path:
        return self.base_dir / "history_summary.txt"

    @property
    def rules_path(self) -> Path:
        return self.base_dir / "rules.md"

    def get_preferences_path(self) -> Path:
        """Get preferences path, expanding ~ if needed."""
        config = self.load_config()
        return Path(config.preferences_path).expanduser()

    def ensure_dirs(self) -> None:
        """Ensure storage directories exist."""
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> Config:
        """Load configuration from file."""
        if self._config is not None:
            return self._config

        if not self.config_path.exists():
            self._config = Config()
            return self._config

        try:
            data = json.loads(self.config_path.read_text())
            self._config = Config.from_dict(data)
        except (json.JSONDecodeError, IOError):
            self._config = Config()

        return self._config

    def save_config(self, config: Config) -> None:
        """Save configuration to file."""
        self.ensure_dirs()
        self.config_path.write_text(json.dumps(config.to_dict(), indent=2))
        self._config = config

    def reset_config(self) -> Config:
        """Reset configuration to defaults."""
        config = Config()
        self.save_config(config)
        return config

    def load_preferences(self) -> str:
        """Load user preferences from file."""
        path = self.get_preferences_path()
        if not path.exists():
            return ""
        return path.read_text()

    def save_preferences(self, content: str) -> None:
        """Save user preferences to file."""
        path = self.get_preferences_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    # Rules management

    def load_rules(self) -> str:
        """Load rules markdown."""
        if not self.rules_path.exists():
            return ""
        return self.rules_path.read_text()

    def save_rules(self, content: str) -> None:
        """Save rules markdown."""
        self.ensure_dirs()
        self.rules_path.write_text(content)

    def append_rule(self, title: str, content: str, rule_type: str = "like") -> None:
        """Append a new rule to rules.md.

        Args:
            title: Rule title (will be ### heading)
            content: Rule content (2-3 sentences)
            rule_type: "like" or "dislike"
        """
        existing = self.load_rules()

        # Initialize structure if empty
        if not existing.strip():
            existing = "# My Discovery Rules\n\n## Likes\n\n## Dislikes\n"

        section_header = "## Likes" if rule_type == "like" else "## Dislikes"
        new_rule = f"\n### {title}\n{content}\n"

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
            updated = existing[:section_end].rstrip() + new_rule + existing[section_end:]
        else:
            # Add the section if it doesn't exist
            updated = existing.rstrip() + f"\n\n{section_header}\n{new_rule}"

        self.save_rules(updated)

    def clear_rules(self) -> None:
        """Clear all rules."""
        if self.rules_path.exists():
            self.rules_path.unlink()

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

    def load_recent_history(self, limit: Optional[int] = None) -> list[HistoryEntry]:
        """Load recent history entries.

        Args:
            limit: Maximum number of entries to return. If None, uses config default.

        Returns:
            List of recent history entries, newest first.
        """
        if limit is None:
            limit = self.load_config().max_recent_history

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

    def get_all_urls(self) -> set[str]:
        """Get all URLs ever shown (to avoid repeating)."""
        return {e.url for e in self.load_all_history()}

    def load_history_summary(self) -> str:
        """Load history summary from file."""
        if not self.summary_path.exists():
            return ""
        return self.summary_path.read_text()

    def save_history_summary(self, summary: str) -> None:
        """Save history summary to file."""
        self.ensure_dirs()
        self.summary_path.write_text(summary)

    def needs_summary_update(self) -> bool:
        """Check if history summary needs to be regenerated.

        Returns True if:
        - Summary doesn't exist and we have history
        - Number of entries since last summary exceeds threshold
        """
        config = self.load_config()
        if not config.summarize_old_history:
            return False

        history = self.load_all_history()
        if not history:
            return False

        if not self.summary_path.exists():
            return len(history) >= config.summary_threshold

        # Check if we have enough new entries since last summary
        # For now, we'll just check total count vs threshold
        # A more sophisticated approach would track last summarized count
        return len(history) >= config.summary_threshold * 2

    def clear_history(self) -> None:
        """Clear all history."""
        if self.history_path.exists():
            self.history_path.unlink()
        if self.summary_path.exists():
            self.summary_path.unlink()

    def count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())

    def build_history_context(self, warn_callback=None) -> str:
        """Build the history context string for the prompt.

        Args:
            warn_callback: Optional callback function to emit warnings.
                           Called with (message: str) when context is too long.

        Returns:
            String with history context (rules, recent items, unextracted likes/dislikes, summary).
        """
        config = self.load_config()

        if not config.history_enabled:
            return ""

        history_parts = []

        # 1. Discovery rules (compact, high signal - extracted patterns)
        rules = self.load_rules()
        if rules.strip():
            history_parts.append(f"<discovery_rules>\n{rules}\n</discovery_rules>")

        # 2. Recent entries (to avoid repeating) - include all, extracted or not
        recent = self.load_recent_history()
        if recent:
            recent_lines = []
            for e in recent:
                feedback_str = f", {e.feedback}" if e.feedback else ", no feedback"
                recent_lines.append(f"- {e.url} ({e.type}{feedback_str})")
            history_parts.append(
                "Recently shown (do not repeat these URLs):\n" + "\n".join(recent_lines)
            )

        # 3. Unextracted liked entries (not yet in rules)
        unextracted_liked = self.get_unextracted_entries("liked")
        if unextracted_liked:
            liked_lines = [f"- {e.url} - \"{e.reason[:100]}...\"" for e in unextracted_liked]
            history_parts.append(
                "Items you've liked (not yet in rules):\n" + "\n".join(liked_lines)
            )

        # 4. Unextracted disliked entries (not yet in rules)
        unextracted_disliked = self.get_unextracted_entries("disliked")
        if unextracted_disliked:
            disliked_lines = [f"- {e.url}" for e in unextracted_disliked]
            history_parts.append(
                "Items you didn't like (not yet in rules):\n" + "\n".join(disliked_lines)
            )

        # 5. Summary (legacy, for old history)
        summary = self.load_history_summary()
        if summary.strip():
            history_parts.append(f"Long-term patterns:\n{summary}")

        if not history_parts:
            return ""

        result = "<history_context>\n" + "\n\n".join(history_parts) + "\n</history_context>"

        # Check total word count and warn if too long
        word_count = self.count_words(result)
        if word_count > 10000 and warn_callback:
            warn_callback(
                f"History context is {word_count:,} words (>10K). "
                f"Consider extracting rules with 'serendipity rules -i' "
                f"or clearing old entries with 'serendipity history --clear'."
            )

        return result

    def build_style_guidance(self) -> str:
        """Build style guidance for the prompt.

        Returns:
            String with style guidance.
        """
        config = self.load_config()
        if config.html_style:
            return f'<style_guidance>\nStyle the HTML output as: {config.html_style}\n</style_guidance>'
        else:
            return '<style_guidance>\nGenerate HTML styling that reflects the user\'s aesthetic taste based on their preferences and the nature of the recommendations.\n</style_guidance>'
