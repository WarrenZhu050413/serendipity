"""Parser for learnings.md structured content.

Provides bidirectional conversion between markdown format and structured list.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Learning:
    """A single learning entry."""

    id: str  # Content-based hash for stable references
    learning_type: str  # "like" or "dislike"
    title: str
    content: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "type": self.learning_type,
            "title": self.title,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Learning":
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            learning_type=data.get("type", "like"),
            title=data.get("title", ""),
            content=data.get("content", ""),
        )


def _generate_id(title: str, content: str) -> str:
    """Generate stable ID from content.

    Uses first 8 chars of SHA-256 hash for short, stable IDs.
    """
    combined = f"{title}:{content}"
    return hashlib.sha256(combined.encode()).hexdigest()[:8]


def parse_learnings(markdown: str) -> list[Learning]:
    """Parse learnings markdown into structured list.

    Expected format:
    ```markdown
    # My Discovery Learnings

    ## Likes

    ### Title 1
    Content here...

    ### Title 2
    More content...

    ## Dislikes

    ### Title 3
    Dislike content...
    ```

    Args:
        markdown: Learnings markdown content

    Returns:
        List of Learning objects
    """
    if not markdown or not markdown.strip():
        return []

    learnings = []
    current_type: Optional[str] = None
    current_title: Optional[str] = None
    current_content_lines: list[str] = []

    def flush_current():
        """Save the current learning if we have one."""
        nonlocal current_title, current_content_lines
        if current_title and current_type:
            content = "\n".join(current_content_lines).strip()
            learnings.append(Learning(
                id=_generate_id(current_title, content),
                learning_type=current_type,
                title=current_title,
                content=content,
            ))
        current_title = None
        current_content_lines = []

    for line in markdown.split("\n"):
        stripped = line.strip()

        # Check for section headers (## Likes or ## Dislikes)
        if stripped.startswith("## "):
            flush_current()
            section = stripped[3:].strip().lower()
            if "like" in section and "dislike" not in section:
                current_type = "like"
            elif "dislike" in section:
                current_type = "dislike"
            else:
                current_type = None
            continue

        # Check for learning title (### Title)
        if stripped.startswith("### "):
            flush_current()
            current_title = stripped[4:].strip()
            continue

        # Check for top-level header (# ...) - skip it
        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue

        # Accumulate content lines
        if current_title is not None:
            current_content_lines.append(line)

    # Flush any remaining learning
    flush_current()

    return learnings


def serialize_learnings(learnings: list[Learning]) -> str:
    """Serialize learnings list back to markdown format.

    Args:
        learnings: List of Learning objects

    Returns:
        Markdown string
    """
    if not learnings:
        return "# My Discovery Learnings\n\n## Likes\n\n## Dislikes\n"

    # Group by type
    likes = [l for l in learnings if l.learning_type == "like"]
    dislikes = [l for l in learnings if l.learning_type == "dislike"]

    lines = ["# My Discovery Learnings", ""]

    # Likes section
    lines.append("## Likes")
    lines.append("")
    for learning in likes:
        lines.append(f"### {learning.title}")
        lines.append(learning.content)
        lines.append("")

    # Dislikes section
    lines.append("## Dislikes")
    lines.append("")
    for learning in dislikes:
        lines.append(f"### {learning.title}")
        lines.append(learning.content)
        lines.append("")

    return "\n".join(lines)


def find_learning_by_id(learnings: list[Learning], learning_id: str) -> Optional[Learning]:
    """Find a learning by its ID.

    Args:
        learnings: List of learnings to search
        learning_id: ID to find

    Returns:
        Learning if found, None otherwise
    """
    for learning in learnings:
        if learning.id == learning_id:
            return learning
    return None


def delete_learning_by_id(learnings: list[Learning], learning_id: str) -> list[Learning]:
    """Remove a learning by ID.

    Args:
        learnings: List of learnings
        learning_id: ID to remove

    Returns:
        New list with learning removed
    """
    return [l for l in learnings if l.id != learning_id]


def update_learning_by_id(
    learnings: list[Learning],
    learning_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
) -> list[Learning]:
    """Update a learning by ID.

    Note: Updating title or content will change the ID since IDs are content-based.

    Args:
        learnings: List of learnings
        learning_id: ID of learning to update
        title: New title (optional)
        content: New content (optional)

    Returns:
        New list with updated learning (including new ID)
    """
    result = []
    for learning in learnings:
        if learning.id == learning_id:
            new_title = title if title is not None else learning.title
            new_content = content if content is not None else learning.content
            result.append(Learning(
                id=_generate_id(new_title, new_content),
                learning_type=learning.learning_type,
                title=new_title,
                content=new_content,
            ))
        else:
            result.append(learning)
    return result


def add_learning(
    learnings: list[Learning],
    learning_type: str,
    title: str,
    content: str,
) -> list[Learning]:
    """Add a new learning.

    Args:
        learnings: Existing list of learnings
        learning_type: "like" or "dislike"
        title: Learning title
        content: Learning content

    Returns:
        New list with learning added
    """
    new_learning = Learning(
        id=_generate_id(title, content),
        learning_type=learning_type,
        title=title,
        content=content,
    )
    return learnings + [new_learning]
