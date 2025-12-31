"""Rule extraction using Claude."""

import json
import re
from dataclasses import dataclass
from typing import Optional

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from serendipity.storage import HistoryEntry

# Model name mapping
MODEL_IDS = {
    "haiku": "claude-3-5-haiku-latest",
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-5-20250514",
}

# Prompts for rule extraction

RULE_EXTRACTION_PROMPT = """Based on these {count} {feedback_type} items, write a concise rule that captures the pattern.

Items:
{items}

Write a rule in this format:
<rule>
<title>Short descriptive title (3-6 words)</title>
<content>2-3 sentences explaining the pattern. Be specific about what ties these together. Focus on underlying qualities, not surface features.</content>
</rule>
"""

AUTO_MATCH_PROMPT = """Given this user-written rule:
<rule>
{rule_text}
</rule>

Which of these items match this rule? Consider both direct matches and items that fit the spirit of the rule.

Items:
{items}

Return as JSON (no markdown, just the object):
{{"matching_urls": ["url1", "url2", ...]}}
"""


@dataclass
class ExtractedRule:
    """A rule extracted from history items."""

    title: str
    content: str
    rule_type: str  # "like" or "dislike"


def _format_items_for_prompt(entries: list[HistoryEntry]) -> str:
    """Format entries for inclusion in prompt."""
    lines = []
    for e in entries:
        reason_preview = e.reason[:150] + "..." if len(e.reason) > 150 else e.reason
        lines.append(f"- {e.url}\n  Reason: {reason_preview}")
    return "\n".join(lines)


async def generate_rule(
    entries: list[HistoryEntry],
    feedback_type: str = "liked",
    model: str = "haiku",
) -> Optional[ExtractedRule]:
    """Generate a rule from selected history entries.

    Args:
        entries: List of history entries to extract rule from
        feedback_type: "liked" or "disliked"
        model: Claude model to use (haiku for speed)

    Returns:
        ExtractedRule if successful, None otherwise
    """
    if not entries:
        return None

    items_text = _format_items_for_prompt(entries)
    prompt = RULE_EXTRACTION_PROMPT.format(
        count=len(entries),
        feedback_type=feedback_type,
        items=items_text,
    )

    options = ClaudeAgentOptions(
        model=MODEL_IDS.get(model, MODEL_IDS["haiku"]),
        system_prompt="You are helping extract patterns from user preferences. Be concise and specific.",
        max_turns=1,
        allowed_tools=[],
    )

    result_text = ""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            result_text = message.result or ""

    # Parse the rule from response
    title_match = re.search(r"<title>(.*?)</title>", result_text, re.DOTALL)
    content_match = re.search(r"<content>(.*?)</content>", result_text, re.DOTALL)

    if title_match and content_match:
        return ExtractedRule(
            title=title_match.group(1).strip(),
            content=content_match.group(1).strip(),
            rule_type="like" if feedback_type == "liked" else "dislike",
        )

    return None


async def find_matching_items(
    rule_text: str,
    entries: list[HistoryEntry],
    model: str = "haiku",
) -> list[str]:
    """Find history entries that match a user-written rule.

    Args:
        rule_text: The rule text written by user
        entries: List of history entries to check
        model: Claude model to use

    Returns:
        List of matching URLs
    """
    if not entries:
        return []

    items_text = _format_items_for_prompt(entries)
    prompt = AUTO_MATCH_PROMPT.format(
        rule_text=rule_text,
        items=items_text,
    )

    options = ClaudeAgentOptions(
        model=MODEL_IDS.get(model, MODEL_IDS["haiku"]),
        system_prompt="You are helping match items to a rule. Return only valid JSON.",
        max_turns=1,
        allowed_tools=[],
    )

    result_text = ""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            result_text = message.result or ""

    # Parse JSON from response
    try:
        # Handle markdown code blocks
        clean = result_text.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)

        data = json.loads(clean)
        return data.get("matching_urls", [])
    except json.JSONDecodeError:
        return []
