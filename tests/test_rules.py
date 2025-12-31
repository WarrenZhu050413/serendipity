"""Tests for serendipity rules module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from serendipity.rules import (
    AUTO_MATCH_PROMPT,
    MODEL_IDS,
    RULE_EXTRACTION_PROMPT,
    ExtractedRule,
    _format_items_for_prompt,
    find_matching_items,
    generate_rule,
)
from serendipity.storage import HistoryEntry


def make_entry(url: str, reason: str) -> HistoryEntry:
    """Helper to create test entries."""
    return HistoryEntry(
        url=url,
        reason=reason,
        type="convergent",
        feedback="liked",
        timestamp="2024-01-15T10:30:00Z",
        session_id="abc123",
    )


class TestModelIds:
    """Tests for model ID configuration."""

    def test_model_ids_exist(self):
        """Test that all expected models are configured."""
        assert "haiku" in MODEL_IDS
        assert "sonnet" in MODEL_IDS
        assert "opus" in MODEL_IDS

    def test_model_ids_format(self):
        """Test that model IDs have expected format."""
        assert "claude" in MODEL_IDS["haiku"]
        assert "claude" in MODEL_IDS["sonnet"]
        assert "claude" in MODEL_IDS["opus"]


class TestExtractedRule:
    """Tests for ExtractedRule dataclass."""

    def test_create_rule(self):
        """Test creating an extracted rule."""
        rule = ExtractedRule(
            title="Japanese Minimalism",
            content="I like clean designs.",
            rule_type="like",
        )
        assert rule.title == "Japanese Minimalism"
        assert rule.content == "I like clean designs."
        assert rule.rule_type == "like"


class TestFormatItemsForPrompt:
    """Tests for _format_items_for_prompt helper."""

    def test_format_single_item(self):
        """Test formatting a single item."""
        entries = [make_entry("https://example.com", "Great content")]
        result = _format_items_for_prompt(entries)
        assert "https://example.com" in result
        assert "Great content" in result

    def test_format_multiple_items(self):
        """Test formatting multiple items."""
        entries = [
            make_entry("https://example1.com", "Content 1"),
            make_entry("https://example2.com", "Content 2"),
        ]
        result = _format_items_for_prompt(entries)
        assert "https://example1.com" in result
        assert "https://example2.com" in result
        assert "Content 1" in result
        assert "Content 2" in result

    def test_truncates_long_reasons(self):
        """Test that long reasons are truncated."""
        long_reason = "x" * 200
        entries = [make_entry("https://example.com", long_reason)]
        result = _format_items_for_prompt(entries)
        assert "..." in result
        assert len(result) < len(long_reason) + 100  # Some overhead for formatting


class TestPrompts:
    """Tests for prompt templates."""

    def test_rule_extraction_prompt_format(self):
        """Test that rule extraction prompt has expected placeholders."""
        assert "{count}" in RULE_EXTRACTION_PROMPT
        assert "{feedback_type}" in RULE_EXTRACTION_PROMPT
        assert "{items}" in RULE_EXTRACTION_PROMPT
        assert "<rule>" in RULE_EXTRACTION_PROMPT
        assert "<title>" in RULE_EXTRACTION_PROMPT
        assert "<content>" in RULE_EXTRACTION_PROMPT

    def test_auto_match_prompt_format(self):
        """Test that auto match prompt has expected placeholders."""
        assert "{rule_text}" in AUTO_MATCH_PROMPT
        assert "{items}" in AUTO_MATCH_PROMPT
        assert "matching_urls" in AUTO_MATCH_PROMPT


class TestGenerateRule:
    """Tests for generate_rule function."""

    @pytest.mark.asyncio
    async def test_empty_entries(self):
        """Test with no entries."""
        result = await generate_rule([], "liked")
        assert result is None

    @pytest.mark.asyncio
    async def test_generation_returns_none_on_empty(self):
        """Test that generate_rule returns None for empty entries."""
        result = await generate_rule([], "liked", model="haiku")
        assert result is None

    def test_parse_rule_from_response(self):
        """Test parsing rule from Claude's response."""
        import re

        response = """
        Here's the rule based on your selections:

        <rule>
        <title>Clean Design Aesthetic</title>
        <content>I appreciate minimalist, uncluttered designs with lots of white space and natural materials.</content>
        </rule>
        """

        title_match = re.search(r"<title>(.*?)</title>", response, re.DOTALL)
        content_match = re.search(r"<content>(.*?)</content>", response, re.DOTALL)

        assert title_match is not None
        assert title_match.group(1).strip() == "Clean Design Aesthetic"
        assert content_match is not None
        assert "minimalist" in content_match.group(1)


class TestFindMatchingItems:
    """Tests for find_matching_items function."""

    @pytest.mark.asyncio
    async def test_empty_entries(self):
        """Test with no entries."""
        result = await find_matching_items("test rule", [])
        assert result == []

    def test_parse_matching_urls(self):
        """Test parsing matching URLs from Claude's response."""
        import json

        response = '{"matching_urls": ["https://example1.com", "https://example2.com"]}'
        data = json.loads(response)
        assert data["matching_urls"] == ["https://example1.com", "https://example2.com"]

    def test_parse_matching_urls_with_markdown(self):
        """Test parsing matching URLs from response with markdown code blocks."""
        import json
        import re

        response = """```json
{"matching_urls": ["https://example1.com", "https://example2.com"]}
```"""

        clean = response.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)

        data = json.loads(clean)
        assert data["matching_urls"] == ["https://example1.com", "https://example2.com"]

    def test_parse_invalid_json(self):
        """Test handling invalid JSON response."""
        import json

        response = "This is not valid JSON"
        try:
            json.loads(response)
            assert False, "Should have raised JSONDecodeError"
        except json.JSONDecodeError:
            pass  # Expected
