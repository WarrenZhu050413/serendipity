"""Tests for serendipity display module."""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from serendipity.display import AgentDisplay, DisplayConfig


class TestDisplayConfig:
    """Tests for DisplayConfig dataclass."""

    def test_default_verbose_false(self):
        """Test default verbose is False."""
        config = DisplayConfig()
        assert config.verbose is False

    def test_verbose_true(self):
        """Test setting verbose to True."""
        config = DisplayConfig(verbose=True)
        assert config.verbose is True


class TestAgentDisplayInitialization:
    """Tests for AgentDisplay initialization."""

    def test_init_with_console(self):
        """Test initialization with console."""
        console = Console()
        config = DisplayConfig()
        display = AgentDisplay(console=console, config=config)
        assert display.console == console
        assert display.config == config
        assert display._pending_tool_use == {}

    def test_init_with_verbose_config(self):
        """Test initialization with verbose config."""
        console = Console()
        config = DisplayConfig(verbose=True)
        display = AgentDisplay(console=console, config=config)
        assert display.config.verbose is True


class TestShowThinking:
    """Tests for show_thinking method."""

    def test_thinking_not_shown_in_normal_mode(self):
        """Test that thinking is hidden in normal mode."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=False)
        display = AgentDisplay(console=console, config=config)

        display.show_thinking("This is my thinking process...")
        console.file.seek(0)
        content = output.getvalue()
        assert "thinking" not in content.lower()

    def test_thinking_shown_in_verbose_mode(self):
        """Test that thinking is shown in verbose mode."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=True)
        display = AgentDisplay(console=console, config=config)

        display.show_thinking("This is my thinking process...")
        content = output.getvalue()
        # Should show the panel with thinking
        assert "thinking" in content.lower() or "This is my thinking" in content

    def test_thinking_truncated_when_long(self):
        """Test that long thinking is truncated."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=True)
        display = AgentDisplay(console=console, config=config)

        long_thinking = "x" * 600  # More than 500 char limit
        display.show_thinking(long_thinking)
        content = output.getvalue()
        # Should contain truncation indicator
        assert "..." in content


class TestShowToolUse:
    """Tests for show_tool_use method."""

    def test_tool_use_registered(self):
        """Test that tool use is registered in pending dict."""
        console = Console(file=StringIO())
        config = DisplayConfig(verbose=False)
        display = AgentDisplay(console=console, config=config)

        display.show_tool_use("WebSearch", "tool-123", {"query": "test query"})
        assert "tool-123" in display._pending_tool_use
        assert display._pending_tool_use["tool-123"]["name"] == "WebSearch"
        assert display._pending_tool_use["tool-123"]["input"]["query"] == "test query"

    def test_websearch_compact_mode(self):
        """Test WebSearch shows query in compact mode."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=False)
        display = AgentDisplay(console=console, config=config)

        display.show_tool_use("WebSearch", "tool-123", {"query": "python best practices"})
        content = output.getvalue()
        assert "WebSearch" in content
        assert "python best practices" in content

    def test_webfetch_compact_mode(self):
        """Test WebFetch shows URL in compact mode."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=False)
        display = AgentDisplay(console=console, config=config)

        display.show_tool_use("WebFetch", "tool-456", {"url": "https://example.com/article"})
        content = output.getvalue()
        assert "WebFetch" in content
        assert "example.com" in content

    def test_webfetch_url_truncation(self):
        """Test long URLs are truncated in compact mode."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=False)
        display = AgentDisplay(console=console, config=config)

        long_url = "https://example.com/" + "x" * 100
        display.show_tool_use("WebFetch", "tool-789", {"url": long_url})
        content = output.getvalue()
        assert "..." in content

    def test_verbose_shows_full_json(self):
        """Test verbose mode shows full JSON input."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=True)
        display = AgentDisplay(console=console, config=config)

        input_data = {"query": "test", "limit": 10}
        display.show_tool_use("WebSearch", "tool-abc", input_data)
        content = output.getvalue()
        # In verbose mode, should show the full JSON
        assert "WebSearch" in content


class TestShowToolResult:
    """Tests for show_tool_result method."""

    def test_tool_result_normal_mode_silent(self):
        """Test that tool result is silent in normal mode."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=False)
        display = AgentDisplay(console=console, config=config)

        # First register a tool use
        display.show_tool_use("WebSearch", "tool-123", {"query": "test"})
        output.truncate(0)
        output.seek(0)

        # Then show result
        display.show_tool_result("tool-123", {"result": "success"}, is_error=False)
        content = output.getvalue()
        # In normal mode, results are not shown
        assert "result" not in content.lower() or content == ""

    def test_tool_result_verbose_mode(self):
        """Test that tool result is shown in verbose mode."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=True)
        display = AgentDisplay(console=console, config=config)

        display.show_tool_use("WebSearch", "tool-123", {"query": "test"})
        display.show_tool_result("tool-123", {"result": "success"}, is_error=False)
        content = output.getvalue()
        assert "Result" in content or "success" in content

    def test_tool_error_verbose_mode(self):
        """Test that tool error is shown in verbose mode."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=True)
        display = AgentDisplay(console=console, config=config)

        display.show_tool_use("WebFetch", "tool-err", {"url": "https://broken.com"})
        display.show_tool_result("tool-err", "Connection failed", is_error=True)
        content = output.getvalue()
        assert "Error" in content


class TestShowText:
    """Tests for show_text method."""

    def test_empty_text_not_shown(self):
        """Test that empty text is not shown."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=True)
        display = AgentDisplay(console=console, config=config)

        display.show_text("")
        display.show_text("   ")
        content = output.getvalue()
        assert content == ""

    def test_text_shown_in_verbose_mode(self):
        """Test that text is shown in verbose mode."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=True)
        display = AgentDisplay(console=console, config=config)

        display.show_text("Some response text")
        content = output.getvalue()
        assert "Some response text" in content

    def test_text_hidden_in_normal_mode(self):
        """Test that text is hidden in normal mode."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=False)
        display = AgentDisplay(console=console, config=config)

        display.show_text("Some response text")
        content = output.getvalue()
        assert "Some response text" not in content


class TestSummarizeInput:
    """Tests for _summarize_input helper method."""

    @pytest.fixture
    def display(self):
        """Create display for testing."""
        return AgentDisplay(
            console=Console(file=StringIO()),
            config=DisplayConfig(verbose=False),
        )

    def test_websearch_summary(self, display):
        """Test WebSearch summary shows query."""
        result = display._summarize_input("WebSearch", {"query": "test query"})
        assert "test query" in result

    def test_webfetch_summary(self, display):
        """Test WebFetch summary shows URL."""
        result = display._summarize_input("WebFetch", {"url": "https://example.com"})
        assert "example.com" in result

    def test_generic_tool_summary(self, display):
        """Test generic tool shows first key-value."""
        result = display._summarize_input("CustomTool", {"param1": "value1", "param2": "value2"})
        assert "param1" in result
        assert "value1" in result

    def test_empty_input_summary(self, display):
        """Test empty input returns empty string."""
        result = display._summarize_input("SomeTool", {})
        assert result == ""

    def test_webfetch_no_url(self, display):
        """Test WebFetch without URL returns empty string."""
        result = display._summarize_input("WebFetch", {})
        assert result == ""

    def test_websearch_no_query(self, display):
        """Test WebSearch without query returns empty string."""
        result = display._summarize_input("WebSearch", {})
        assert result == ""


class TestFormatContent:
    """Tests for _format_content helper method."""

    @pytest.fixture
    def display(self):
        """Create display for testing."""
        return AgentDisplay(
            console=Console(file=StringIO()),
            config=DisplayConfig(verbose=False),
        )

    def test_format_json_string(self, display):
        """Test formatting JSON string content."""
        json_str = '{"key": "value"}'
        result = display._format_content(json_str)
        # Should be pretty-printed
        assert "key" in result
        assert "value" in result

    def test_format_dict(self, display):
        """Test formatting dict content."""
        content = {"key": "value", "number": 42}
        result = display._format_content(content)
        assert "key" in result
        assert "value" in result
        assert "42" in result

    def test_format_plain_string(self, display):
        """Test formatting plain string content."""
        result = display._format_content("Just some text")
        assert result == "Just some text"

    def test_format_invalid_json_string(self, display):
        """Test formatting invalid JSON string returns as-is."""
        result = display._format_content("Not JSON {broken")
        assert result == "Not JSON {broken"

    def test_format_other_types(self, display):
        """Test formatting other types."""
        result = display._format_content(12345)
        assert result == "12345"

        result = display._format_content(["list", "items"])
        assert "list" in result


class TestAgentDisplayIntegration:
    """Integration tests for AgentDisplay."""

    def test_full_tool_use_flow(self):
        """Test complete tool use flow: request -> result."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=True)
        display = AgentDisplay(console=console, config=config)

        # Show tool use
        display.show_tool_use("WebSearch", "id-1", {"query": "python tutorials"})

        # Show result
        display.show_tool_result("id-1", {"results": ["result1", "result2"]}, is_error=False)

        content = output.getvalue()
        assert "WebSearch" in content
        assert "Result" in content

    def test_multiple_tools_tracked(self):
        """Test that multiple tool uses are tracked separately."""
        console = Console(file=StringIO())
        config = DisplayConfig(verbose=False)
        display = AgentDisplay(console=console, config=config)

        display.show_tool_use("WebSearch", "id-1", {"query": "test1"})
        display.show_tool_use("WebFetch", "id-2", {"url": "https://example.com"})
        display.show_tool_use("WebSearch", "id-3", {"query": "test2"})

        assert len(display._pending_tool_use) == 3
        assert display._pending_tool_use["id-1"]["name"] == "WebSearch"
        assert display._pending_tool_use["id-2"]["name"] == "WebFetch"
        assert display._pending_tool_use["id-3"]["name"] == "WebSearch"

    def test_mixed_output_flow(self):
        """Test mixed thinking, tool use, and text output."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        config = DisplayConfig(verbose=True)
        display = AgentDisplay(console=console, config=config)

        display.show_thinking("Let me search for this...")
        display.show_tool_use("WebSearch", "id-1", {"query": "example"})
        display.show_tool_result("id-1", "Found results", is_error=False)
        display.show_text("Here are my findings...")

        content = output.getvalue()
        # All components should be present in verbose mode
        assert "WebSearch" in content
        assert "findings" in content
