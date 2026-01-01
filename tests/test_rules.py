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

    @pytest.mark.asyncio
    async def test_generate_rule_with_mocked_sdk(self):
        """Test generate_rule with mocked SDK response."""
        from claude_agent_sdk import ResultMessage

        # Create mock ResultMessage with proper response
        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = """<rule>
<title>Minimalist Design</title>
<content>I appreciate clean, uncluttered designs with lots of white space.</content>
</rule>"""

        async def mock_query(*args, **kwargs):
            yield mock_result

        with patch("serendipity.rules.query", mock_query):
            entries = [
                make_entry("https://example.com/1", "Clean design with white space"),
                make_entry("https://example.com/2", "Minimal and elegant"),
            ]
            result = await generate_rule(entries, "liked", model="haiku")

            assert result is not None
            assert result.title == "Minimalist Design"
            assert "uncluttered" in result.content
            assert result.rule_type == "like"

    @pytest.mark.asyncio
    async def test_generate_rule_disliked(self):
        """Test generate_rule with disliked feedback type."""
        from claude_agent_sdk import ResultMessage

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = """<rule>
<title>Cluttered Interfaces</title>
<content>I don't like busy, overwhelming interfaces with too many elements.</content>
</rule>"""

        async def mock_query(*args, **kwargs):
            yield mock_result

        with patch("serendipity.rules.query", mock_query):
            entries = [make_entry("https://example.com", "Too busy")]
            result = await generate_rule(entries, "disliked", model="haiku")

            assert result is not None
            assert result.rule_type == "dislike"

    @pytest.mark.asyncio
    async def test_generate_rule_returns_none_on_invalid_response(self):
        """Test generate_rule returns None when response doesn't parse."""
        from claude_agent_sdk import ResultMessage

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = "This response has no valid rule tags"

        async def mock_query(*args, **kwargs):
            yield mock_result

        with patch("serendipity.rules.query", mock_query):
            entries = [make_entry("https://example.com", "Some reason")]
            result = await generate_rule(entries, "liked")

            assert result is None

    @pytest.mark.asyncio
    async def test_generate_rule_uses_correct_model(self):
        """Test that generate_rule passes correct model ID."""
        from claude_agent_sdk import ResultMessage

        captured_options = []

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = "<rule><title>Test</title><content>Test</content></rule>"

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_result

        with patch("serendipity.rules.query", mock_query):
            entries = [make_entry("https://example.com", "Some reason")]
            await generate_rule(entries, "liked", model="sonnet")

            assert len(captured_options) == 1
            assert "sonnet" in captured_options[0].model


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

    @pytest.mark.asyncio
    async def test_find_matching_items_with_mocked_sdk(self):
        """Test find_matching_items with mocked SDK response."""
        from claude_agent_sdk import ResultMessage

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = '{"matching_urls": ["https://example1.com", "https://example2.com"]}'

        async def mock_query(*args, **kwargs):
            yield mock_result

        with patch("serendipity.rules.query", mock_query):
            entries = [
                make_entry("https://example1.com", "Clean design"),
                make_entry("https://example2.com", "Minimal layout"),
                make_entry("https://example3.com", "Busy interface"),
            ]
            result = await find_matching_items("I like minimalist design", entries)

            assert len(result) == 2
            assert "https://example1.com" in result
            assert "https://example2.com" in result

    @pytest.mark.asyncio
    async def test_find_matching_items_with_markdown_response(self):
        """Test find_matching_items handles markdown code blocks."""
        from claude_agent_sdk import ResultMessage

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = """```json
{"matching_urls": ["https://example.com"]}
```"""

        async def mock_query(*args, **kwargs):
            yield mock_result

        with patch("serendipity.rules.query", mock_query):
            entries = [make_entry("https://example.com", "Test")]
            result = await find_matching_items("test rule", entries)

            assert result == ["https://example.com"]

    @pytest.mark.asyncio
    async def test_find_matching_items_returns_empty_on_invalid_json(self):
        """Test find_matching_items returns empty list on invalid JSON."""
        from claude_agent_sdk import ResultMessage

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = "This is not valid JSON at all"

        async def mock_query(*args, **kwargs):
            yield mock_result

        with patch("serendipity.rules.query", mock_query):
            entries = [make_entry("https://example.com", "Test")]
            result = await find_matching_items("test rule", entries)

            assert result == []

    @pytest.mark.asyncio
    async def test_find_matching_items_returns_empty_on_missing_key(self):
        """Test find_matching_items returns empty when key is missing."""
        from claude_agent_sdk import ResultMessage

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = '{"wrong_key": ["url1", "url2"]}'

        async def mock_query(*args, **kwargs):
            yield mock_result

        with patch("serendipity.rules.query", mock_query):
            entries = [make_entry("https://example.com", "Test")]
            result = await find_matching_items("test rule", entries)

            assert result == []

    @pytest.mark.asyncio
    async def test_find_matching_items_uses_correct_model(self):
        """Test that find_matching_items passes correct model ID."""
        from claude_agent_sdk import ResultMessage

        captured_options = []

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = '{"matching_urls": []}'

        async def mock_query(prompt, options):
            captured_options.append(options)
            yield mock_result

        with patch("serendipity.rules.query", mock_query):
            entries = [make_entry("https://example.com", "Test")]
            await find_matching_items("test rule", entries, model="opus")

            assert len(captured_options) == 1
            assert "opus" in captured_options[0].model
