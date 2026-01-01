"""Storage manager for serendipity history and preferences.

Configuration is now in settings.yaml (via TypesConfig).
This module handles history.jsonl, learnings.md, and output files.

Supports multi-profile storage via ProfileManager.
"""

import json
import os
import shutil
import sys
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml
from copy import deepcopy

if TYPE_CHECKING:
    from serendipity.config.types import TypesConfig


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


@dataclass
class VersionInfo:
    """Information about a version backup."""

    version_id: str  # Timestamp-based ID (e.g., "20251231_143022")
    timestamp: str  # ISO format timestamp
    preview: str  # First ~100 chars of content
    file_path: Path  # Path to the backup file

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version_id": self.version_id,
            "timestamp": self.timestamp,
            "preview": self.preview,
        }


class ProfileManager:
    """Manages multiple serendipity profiles.

    Profiles are stored in ~/.serendipity/profiles/{name}/ directories.
    The active profile is tracked in ~/.serendipity/profiles.yaml.
    """

    DEFAULT_PROFILE = "default"

    def __init__(self, root_dir: Optional[Path] = None):
        """Initialize profile manager.

        Args:
            root_dir: Root directory for serendipity. Defaults to ~/.serendipity
        """
        self.root_dir = root_dir or Path.home() / ".serendipity"
        self.profiles_dir = self.root_dir / "profiles"
        self.registry_path = self.root_dir / "profiles.yaml"

    def _load_registry(self) -> dict:
        """Load profiles registry."""
        if not self.registry_path.exists():
            return {"active": self.DEFAULT_PROFILE, "profiles": [self.DEFAULT_PROFILE]}
        try:
            return yaml.safe_load(self.registry_path.read_text()) or {}
        except yaml.YAMLError:
            return {"active": self.DEFAULT_PROFILE, "profiles": [self.DEFAULT_PROFILE]}

    def _save_registry(self, registry: dict) -> None:
        """Save profiles registry."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(yaml.dump(registry, default_flow_style=False))

    def list_profiles(self) -> list[str]:
        """List all available profiles."""
        registry = self._load_registry()
        profiles = registry.get("profiles", [self.DEFAULT_PROFILE])
        # Also check filesystem for any profiles not in registry
        if self.profiles_dir.exists():
            for path in self.profiles_dir.iterdir():
                if path.is_dir() and path.name not in profiles:
                    profiles.append(path.name)
        return sorted(profiles)

    def get_active_profile(self) -> str:
        """Get the currently active profile name.

        Checks SERENDIPITY_PROFILE environment variable first.
        """
        env_profile = os.environ.get("SERENDIPITY_PROFILE")
        if env_profile:
            return env_profile
        registry = self._load_registry()
        return registry.get("active", self.DEFAULT_PROFILE)

    def set_active_profile(self, name: str) -> None:
        """Set the active profile.

        Args:
            name: Profile name to activate

        Raises:
            ValueError: If profile doesn't exist
        """
        if not self.profile_exists(name):
            raise ValueError(f"Profile '{name}' does not exist")
        registry = self._load_registry()
        registry["active"] = name
        self._save_registry(registry)

    def profile_exists(self, name: str) -> bool:
        """Check if a profile exists."""
        return self.get_profile_path(name).exists()

    def get_profile_path(self, name: str) -> Path:
        """Get the directory path for a profile."""
        return self.profiles_dir / name

    def create_profile(
        self,
        name: str,
        from_profile: Optional[str] = None,
    ) -> Path:
        """Create a new profile.

        Args:
            name: Name for the new profile
            from_profile: Optional profile to copy from

        Returns:
            Path to the new profile directory

        Raises:
            ValueError: If profile already exists or source doesn't exist
        """
        if self.profile_exists(name):
            raise ValueError(f"Profile '{name}' already exists")

        profile_path = self.get_profile_path(name)

        if from_profile:
            if not self.profile_exists(from_profile):
                raise ValueError(f"Source profile '{from_profile}' does not exist")
            source_path = self.get_profile_path(from_profile)
            shutil.copytree(source_path, profile_path)
        else:
            profile_path.mkdir(parents=True, exist_ok=True)
            # Create loaders directory
            (profile_path / "loaders").mkdir(exist_ok=True)

        # Update registry
        registry = self._load_registry()
        if "profiles" not in registry:
            registry["profiles"] = []
        if name not in registry["profiles"]:
            registry["profiles"].append(name)
        self._save_registry(registry)

        return profile_path

    def delete_profile(self, name: str) -> None:
        """Delete a profile.

        Args:
            name: Profile to delete

        Raises:
            ValueError: If profile doesn't exist or is the active profile
        """
        if not self.profile_exists(name):
            raise ValueError(f"Profile '{name}' does not exist")

        active = self.get_active_profile()
        if name == active:
            raise ValueError(f"Cannot delete active profile '{name}'. Switch to another profile first.")

        # Delete directory
        profile_path = self.get_profile_path(name)
        shutil.rmtree(profile_path)

        # Update registry
        registry = self._load_registry()
        if name in registry.get("profiles", []):
            registry["profiles"].remove(name)
        self._save_registry(registry)

    def rename_profile(self, old_name: str, new_name: str) -> None:
        """Rename a profile.

        Args:
            old_name: Current profile name
            new_name: New profile name

        Raises:
            ValueError: If old profile doesn't exist or new name is taken
        """
        if not self.profile_exists(old_name):
            raise ValueError(f"Profile '{old_name}' does not exist")
        if self.profile_exists(new_name):
            raise ValueError(f"Profile '{new_name}' already exists")

        old_path = self.get_profile_path(old_name)
        new_path = self.get_profile_path(new_name)
        old_path.rename(new_path)

        # Update registry
        registry = self._load_registry()
        if old_name in registry.get("profiles", []):
            registry["profiles"].remove(old_name)
            registry["profiles"].append(new_name)
        if registry.get("active") == old_name:
            registry["active"] = new_name
        self._save_registry(registry)

    def export_profile(
        self,
        name: str,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Export a profile to a tar.gz archive.

        Args:
            name: Profile to export
            output_path: Output file path. Defaults to {name}.tar.gz in current dir

        Returns:
            Path to the created archive

        Raises:
            ValueError: If profile doesn't exist
        """
        if not self.profile_exists(name):
            raise ValueError(f"Profile '{name}' does not exist")

        if output_path is None:
            output_path = Path.cwd() / f"{name}.tar.gz"

        profile_path = self.get_profile_path(name)

        with tarfile.open(output_path, "w:gz") as tar:
            # Add profile directory with its name as the root
            tar.add(profile_path, arcname=name)

        return output_path

    def import_profile(
        self,
        archive_path: Path,
        name: Optional[str] = None,
    ) -> str:
        """Import a profile from a tar.gz archive.

        Args:
            archive_path: Path to the archive file
            name: Optional name override. If not provided, uses directory name from archive

        Returns:
            Name of the imported profile

        Raises:
            ValueError: If archive is invalid or profile already exists
        """
        if not archive_path.exists():
            raise ValueError(f"Archive not found: {archive_path}")

        with tarfile.open(archive_path, "r:gz") as tar:
            # Find the root directory name in the archive
            members = tar.getmembers()
            if not members:
                raise ValueError("Empty archive")

            # Get the root directory name
            root_name = members[0].name.split("/")[0]

            # Use provided name or root name
            profile_name = name or root_name

            if self.profile_exists(profile_name):
                raise ValueError(f"Profile '{profile_name}' already exists")

            # Extract to a temp location first
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                tar.extractall(temp_dir)
                extracted_path = Path(temp_dir) / root_name

                # Move to profiles directory
                profile_path = self.get_profile_path(profile_name)
                shutil.copytree(extracted_path, profile_path)

        # Update registry
        registry = self._load_registry()
        if "profiles" not in registry:
            registry["profiles"] = []
        if profile_name not in registry["profiles"]:
            registry["profiles"].append(profile_name)
        self._save_registry(registry)

        return profile_name

    def ensure_default_profile(self) -> None:
        """Ensure the default profile exists."""
        if not self.profile_exists(self.DEFAULT_PROFILE):
            self.create_profile(self.DEFAULT_PROFILE)

    def add_loaders_to_path(self, profile_name: Optional[str] = None) -> None:
        """Add profile's loaders directory to Python path.

        Args:
            profile_name: Profile name. Defaults to active profile.
        """
        name = profile_name or self.get_active_profile()
        loaders_path = self.get_profile_path(name) / "loaders"
        if loaders_path.exists() and str(loaders_path) not in sys.path:
            sys.path.insert(0, str(loaders_path))


class StorageManager:
    """Manages serendipity storage: history, learnings, and output files.

    Supports multi-profile storage. Uses ProfileManager to determine base directory.
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        profile: Optional[str] = None,
        profile_manager: Optional[ProfileManager] = None,
    ):
        """Initialize storage manager.

        Args:
            base_dir: Base directory for storage. If provided, overrides profile-based resolution.
            profile: Profile name to use. Defaults to active profile.
            profile_manager: ProfileManager instance. Created if not provided.
        """
        if base_dir:
            # Direct base_dir takes precedence (for testing or explicit paths)
            self.base_dir = base_dir
            self.profile_manager = None
            self.profile_name = None
        else:
            # Use profile-based resolution
            self.profile_manager = profile_manager or ProfileManager()
            self.profile_name = profile or self.profile_manager.get_active_profile()
            self.profile_manager.ensure_default_profile()
            self.base_dir = self.profile_manager.get_profile_path(self.profile_name)
            # Add profile's loaders to Python path
            self.profile_manager.add_loaders_to_path(self.profile_name)

    @property
    def settings_path(self) -> Path:
        return self.base_dir / "settings.yaml"

    def load_config(self) -> "TypesConfig":
        """Load TypesConfig with proper variable context for this profile.

        This is the preferred way to load config as it handles template
        variable expansion automatically.

        Returns:
            TypesConfig with {profile_dir}, {profile_name}, {home} expanded
        """
        from serendipity.config.types import TypesConfig, build_variable_context

        context = build_variable_context(
            profile_dir=self.base_dir,
            profile_name=self.profile_name,
        )
        return TypesConfig.from_yaml(self.settings_path, variable_context=context)

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
    def style_path(self) -> Path:
        return self.base_dir / "style.css"

    @property
    def output_dir(self) -> Path:
        return self.base_dir / "output"

    @property
    def prompts_dir(self) -> Path:
        return self.base_dir / "prompts"

    def get_prompt_path(self, name: str, default_content: str) -> Path:
        """Get user prompt path, creating from default if missing.

        Auto-creates on first run so users can immediately see/edit.

        Args:
            name: Prompt filename (e.g., "discovery.txt")
            default_content: Default content from package resource

        Returns:
            Path to the user's prompt file
        """
        path = self.prompts_dir / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default_content)
        return path

    def prompt_is_customized(self, name: str, default_content: str) -> bool:
        """Check if user has modified this prompt from package default.

        Args:
            name: Prompt filename (e.g., "discovery.txt")
            default_content: Default content from package resource

        Returns:
            True if user has customized the prompt
        """
        path = self.prompts_dir / name
        if not path.exists():
            return False
        return path.read_text() != default_content

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

    def get_style_path(self, default_content: str) -> Path:
        """Get style path, writing default content on first use.

        Args:
            default_content: Default CSS content to write if user style doesn't exist

        Returns:
            Path to the user's style file
        """
        if not self.style_path.exists():
            self.style_path.parent.mkdir(parents=True, exist_ok=True)
            self.style_path.write_text(default_content)

        return self.style_path

    def style_is_customized(self, default_content: str) -> bool:
        """Check if user has modified the style from package default.

        Args:
            default_content: Default content from package resource

        Returns:
            True if user has customized the style
        """
        if not self.style_path.exists():
            return False
        return self.style_path.read_text() != default_content

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

    # ============================================================
    # New API methods for web UI integration
    # ============================================================

    def save_taste(self, content: str) -> None:
        """Save taste profile content.

        Args:
            content: Markdown content for taste.md
        """
        self.ensure_dirs()
        self.taste_path.write_text(content)

    def delete_history_entry(self, url: str) -> bool:
        """Delete a history entry by URL.

        Args:
            url: URL of the entry to delete

        Returns:
            True if entry was found and deleted, False otherwise.
        """
        if not self.history_path.exists():
            return False

        entries = self.load_all_history()
        original_count = len(entries)

        # Filter out entries with matching URL
        entries = [e for e in entries if e.url != url]

        if len(entries) == original_count:
            return False

        # Rewrite the file
        self.history_path.unlink()
        if entries:
            self.append_history(entries)

        return True

    def update_settings_yaml(self, updates: dict) -> None:
        """Deep merge partial updates into settings.yaml.

        Args:
            updates: Dictionary of updates to merge. Supports nested paths.
                     Example: {"model": "sonnet", "approaches": {"convergent": {"enabled": False}}}
        """
        # Load current settings
        if self.settings_path.exists():
            current = yaml.safe_load(self.settings_path.read_text()) or {}
        else:
            current = {}

        # Deep merge updates
        merged = self._deep_merge(current, updates)

        # Write back
        self.ensure_dirs()
        self.settings_path.write_text(yaml.dump(merged, default_flow_style=False, sort_keys=False))

    def _deep_merge(self, base: dict, updates: dict) -> dict:
        """Deep merge two dictionaries.

        Args:
            base: Base dictionary
            updates: Updates to merge in

        Returns:
            Merged dictionary
        """
        result = deepcopy(base)
        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    # ============================================================
    # Version history support
    # ============================================================

    @property
    def versions_dir(self) -> Path:
        """Directory for version backups."""
        return self.base_dir / ".versions"

    def _get_version_dir(self, file_path: Path) -> Path:
        """Get the version directory for a specific file.

        Args:
            file_path: Path to the file

        Returns:
            Path to the version directory for this file
        """
        # Use the filename as the subdirectory name
        return self.versions_dir / file_path.name

    def save_with_version(self, file_path: Path, content: str) -> str:
        """Save content and create a version backup.

        Args:
            file_path: Path to the file to save
            content: New content to write

        Returns:
            Version ID of the backup created
        """
        # Create version backup if file exists
        version_id = ""
        if file_path.exists():
            version_id = self._create_version_backup(file_path)

        # Write new content
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        return version_id

    def _create_version_backup(self, file_path: Path) -> str:
        """Create a version backup of a file.

        Args:
            file_path: Path to the file to backup

        Returns:
            Version ID of the backup
        """
        version_dir = self._get_version_dir(file_path)
        version_dir.mkdir(parents=True, exist_ok=True)

        # Generate version ID from timestamp
        now = datetime.now()
        version_id = now.strftime("%Y%m%d_%H%M%S")

        # Copy file to version directory
        backup_path = version_dir / f"{version_id}.bak"
        shutil.copy2(file_path, backup_path)

        return version_id

    def list_versions(self, file_path: Path, limit: int = 50) -> list[VersionInfo]:
        """List available versions for a file.

        Args:
            file_path: Path to the file
            limit: Maximum number of versions to return

        Returns:
            List of VersionInfo, newest first
        """
        version_dir = self._get_version_dir(file_path)
        if not version_dir.exists():
            return []

        versions = []
        for backup_file in sorted(version_dir.glob("*.bak"), reverse=True):
            if len(versions) >= limit:
                break

            version_id = backup_file.stem
            try:
                # Parse timestamp from version ID
                dt = datetime.strptime(version_id, "%Y%m%d_%H%M%S")
                timestamp = dt.isoformat()
            except ValueError:
                timestamp = ""

            # Read preview
            try:
                content = backup_file.read_text()
                preview = content[:100].replace("\n", " ").strip()
                if len(content) > 100:
                    preview += "..."
            except Exception:
                preview = "(unable to read)"

            versions.append(VersionInfo(
                version_id=version_id,
                timestamp=timestamp,
                preview=preview,
                file_path=backup_file,
            ))

        return versions

    def get_version_content(self, file_path: Path, version_id: str) -> Optional[str]:
        """Get the content of a specific version.

        Args:
            file_path: Path to the original file
            version_id: Version ID to retrieve

        Returns:
            Content of the version, or None if not found
        """
        version_dir = self._get_version_dir(file_path)
        backup_path = version_dir / f"{version_id}.bak"

        if not backup_path.exists():
            return None

        return backup_path.read_text()

    def restore_version(self, file_path: Path, version_id: str) -> Optional[str]:
        """Restore a file to a previous version.

        Creates a backup of current content before restoring.

        Args:
            file_path: Path to the file to restore
            version_id: Version ID to restore to

        Returns:
            The restored content, or None if version not found
        """
        # Get the version content
        content = self.get_version_content(file_path, version_id)
        if content is None:
            return None

        # Backup current content before restoring
        if file_path.exists():
            self._create_version_backup(file_path)

        # Restore the version
        file_path.write_text(content)

        return content
