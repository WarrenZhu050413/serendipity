"""Tests for serendipity agent module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from serendipity.agent import SerendipityAgent


class TestParseJson:
    """Tests for _parse_json method."""

    @pytest.fixture
    def agent(self):
        """Create agent for testing."""
        return SerendipityAgent(console=Console())

    def test_parse_output_tags(self, agent):
        """Test parsing JSON from <output> tags."""
        text = """
        Here's the result:
        <output>
        {"convergent": [{"url": "https://example.com", "reason": "test"}], "divergent": []}
        </output>
        """
        result = agent._parse_json(text)
        assert len(result["convergent"]) == 1
        assert result["convergent"][0]["url"] == "https://example.com"

    def test_parse_markdown_code_block(self, agent):
        """Test parsing JSON from markdown code block."""
        text = """
        Here's the result:
        ```json
        {"convergent": [{"url": "https://example.com", "reason": "test"}], "divergent": []}
        ```
        """
        result = agent._parse_json(text)
        assert len(result["convergent"]) == 1
        assert result["convergent"][0]["url"] == "https://example.com"

    def test_parse_raw_json(self, agent):
        """Test parsing raw JSON object."""
        text = """
        Some text before
        {"convergent": [{"url": "https://example.com", "reason": "test"}], "divergent": []}
        Some text after
        """
        result = agent._parse_json(text)
        assert len(result["convergent"]) == 1

    def test_parse_malformed_json_returns_empty(self, agent):
        """Test that malformed JSON returns empty structure."""
        text = "This is not JSON at all, just plain text."
        result = agent._parse_json(text)
        assert result == {"convergent": [], "divergent": []}

    def test_parse_output_tags_priority(self, agent):
        """Test that <output> tags take priority over code blocks."""
        text = """
        ```json
        {"convergent": [{"url": "https://wrong.com", "reason": "wrong"}], "divergent": []}
        ```
        <output>
        {"convergent": [{"url": "https://correct.com", "reason": "correct"}], "divergent": []}
        </output>
        """
        result = agent._parse_json(text)
        assert result["convergent"][0]["url"] == "https://correct.com"

    def test_parse_with_html_style(self, agent):
        """Test parsing JSON with html_style field."""
        text = """
        <output>
        {
            "convergent": [],
            "divergent": [],
            "html_style": {
                "description": "Minimal dark theme",
                "css": "body { background: #1a1a1a; }"
            }
        }
        </output>
        """
        result = agent._parse_json(text)
        assert "html_style" in result
        assert result["html_style"]["description"] == "Minimal dark theme"


class TestGetMcpServers:
    """Tests for _get_mcp_servers method."""

    def test_no_servers_when_no_context_manager(self):
        """Test that no MCP servers are returned without context manager."""
        agent = SerendipityAgent(console=Console(), context_manager=None)
        servers = agent._get_mcp_servers()
        assert servers == {}

    def test_mcp_servers_from_context_manager(self):
        """Test that MCP servers come from context manager."""
        mock_manager = MagicMock()
        mock_manager.get_mcp_servers.return_value = {
            "whorl": {
                "url": "http://localhost:8081/mcp/",
                "type": "http",
                "headers": {"X-Password": "whorl"},
            }
        }
        agent = SerendipityAgent(console=Console(), context_manager=mock_manager)
        servers = agent._get_mcp_servers()
        assert "whorl" in servers
        assert servers["whorl"]["type"] == "http"


class TestAllowedTools:
    """Tests for allowed tools list building."""

    def test_base_tools_always_present(self):
        """Test that WebFetch and WebSearch are always in allowed tools."""
        agent = SerendipityAgent(console=Console())
        tools = agent._get_allowed_tools()
        assert "WebFetch" in tools
        assert "WebSearch" in tools

    def test_tools_from_context_manager(self):
        """Test that additional tools come from context manager."""
        mock_manager = MagicMock()
        mock_manager.get_allowed_tools.return_value = [
            "mcp__whorl__text_search_text_search_post",
            "mcp__whorl__agent_search_agent_search_post",
        ]
        agent = SerendipityAgent(console=Console(), context_manager=mock_manager)
        tools = agent._get_allowed_tools()
        assert "WebFetch" in tools
        assert "WebSearch" in tools
        assert "mcp__whorl__text_search_text_search_post" in tools
        assert "mcp__whorl__agent_search_agent_search_post" in tools


class TestSystemPromptHints:
    """Tests for system prompt hints."""

    def test_no_hints_without_context_manager(self):
        """Test that no hints are returned without context manager."""
        agent = SerendipityAgent(console=Console())
        hints = agent._get_system_prompt_hints()
        assert hints == ""

    def test_hints_from_context_manager(self):
        """Test that hints come from context manager."""
        mock_manager = MagicMock()
        mock_manager.get_system_prompt_hints.return_value = "Search Whorl FIRST"
        agent = SerendipityAgent(console=Console(), context_manager=mock_manager)
        hints = agent._get_system_prompt_hints()
        assert "Search Whorl FIRST" in hints


class TestAgentInitialization:
    """Tests for SerendipityAgent initialization."""

    def test_default_initialization(self):
        """Test default agent initialization."""
        agent = SerendipityAgent(console=Console())
        assert agent.model == "opus"
        assert agent.verbose is False
        assert agent.context_manager is None

    def test_with_context_manager(self):
        """Test initialization with context manager."""
        mock_manager = MagicMock()
        agent = SerendipityAgent(console=Console(), context_manager=mock_manager)
        assert agent.context_manager == mock_manager

    def test_model_parameter(self):
        """Test different model parameters."""
        for model in ["haiku", "sonnet", "opus"]:
            agent = SerendipityAgent(console=Console(), model=model)
            assert agent.model == model


class TestResumeCommand:
    """Tests for get_resume_command method."""

    def test_no_session_returns_none(self):
        """Test that no session returns None."""
        agent = SerendipityAgent(console=Console())
        assert agent.get_resume_command() is None

    def test_session_returns_command(self):
        """Test that session ID returns proper command."""
        agent = SerendipityAgent(console=Console())
        agent.last_session_id = "abc123"
        cmd = agent.get_resume_command()
        assert cmd == "claude -r abc123"


class TestGetMoreSessionFeedback:
    """Tests for get_more with session_feedback parameter."""

    @pytest.fixture
    def agent(self):
        """Create agent for testing."""
        return SerendipityAgent(console=Console())

    def test_get_more_accepts_session_feedback_param(self, agent):
        """Test that get_more accepts session_feedback parameter."""
        import inspect
        sig = inspect.signature(agent.get_more)
        params = list(sig.parameters.keys())
        assert "session_feedback" in params

    def test_get_more_sync_accepts_session_feedback_param(self, agent):
        """Test that get_more_sync accepts session_feedback parameter."""
        import inspect
        sig = inspect.signature(agent.get_more_sync)
        params = list(sig.parameters.keys())
        assert "session_feedback" in params

    def test_session_feedback_default_is_none(self, agent):
        """Test that session_feedback defaults to None."""
        import inspect
        sig = inspect.signature(agent.get_more)
        session_feedback_param = sig.parameters["session_feedback"]
        assert session_feedback_param.default is None

    def test_build_feedback_context_with_liked(self, agent):
        """Test that liked items are included in feedback context."""
        session_feedback = [
            {"url": "https://liked1.com", "feedback": "liked"},
            {"url": "https://liked2.com", "feedback": "liked"},
        ]

        liked = [f["url"] for f in session_feedback if f.get("feedback") == "liked"]
        assert len(liked) == 2
        assert "https://liked1.com" in liked
        assert "https://liked2.com" in liked

    def test_build_feedback_context_with_disliked(self, agent):
        """Test that disliked items are included in feedback context."""
        session_feedback = [
            {"url": "https://disliked1.com", "feedback": "disliked"},
        ]

        disliked = [f["url"] for f in session_feedback if f.get("feedback") == "disliked"]
        assert len(disliked) == 1
        assert "https://disliked1.com" in disliked

    def test_build_feedback_context_mixed(self, agent):
        """Test handling of mixed liked/disliked feedback."""
        session_feedback = [
            {"url": "https://liked.com", "feedback": "liked"},
            {"url": "https://disliked.com", "feedback": "disliked"},
            {"url": "https://liked2.com", "feedback": "liked"},
        ]

        liked = [f["url"] for f in session_feedback if f.get("feedback") == "liked"]
        disliked = [f["url"] for f in session_feedback if f.get("feedback") == "disliked"]

        assert len(liked) == 2
        assert len(disliked) == 1

    def test_empty_session_feedback_produces_no_context(self, agent):
        """Test that empty session_feedback produces no feedback context."""
        session_feedback = []

        liked = [f["url"] for f in session_feedback if f.get("feedback") == "liked"]
        disliked = [f["url"] for f in session_feedback if f.get("feedback") == "disliked"]

        assert liked == []
        assert disliked == []
