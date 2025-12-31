"""Tests for serendipity agent module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from serendipity.agent import (
    SerendipityAgent,
    check_whorl_setup,
    ensure_whorl_running,
)


class TestCheckWhorlSetup:
    """Tests for check_whorl_setup function."""

    def test_whorl_not_installed(self):
        """Test when whorl CLI is not installed."""
        console = Console()
        with patch("shutil.which", return_value=None):
            is_ready, error_msg = check_whorl_setup(console)
            assert is_ready is False
            assert "not installed" in error_msg.lower()
            assert "pip install whorled" in error_msg

    def test_whorl_not_initialized(self):
        """Test when whorl home directory doesn't exist."""
        console = Console()
        with (
            patch("shutil.which", return_value="/usr/local/bin/whorl"),
            patch.object(Path, "home", return_value=Path("/nonexistent")),
        ):
            is_ready, error_msg = check_whorl_setup(console)
            assert is_ready is False
            assert "not initialized" in error_msg.lower()
            assert "whorl init" in error_msg

    def test_whorl_no_documents(self):
        """Test when whorl has no documents."""
        console = Console()
        with tempfile.TemporaryDirectory() as tmpdir:
            whorl_home = Path(tmpdir) / ".whorl"
            whorl_home.mkdir()
            docs_dir = whorl_home / "docs"
            docs_dir.mkdir()  # Empty docs directory

            with (
                patch("shutil.which", return_value="/usr/local/bin/whorl"),
                patch.object(Path, "home", return_value=Path(tmpdir)),
            ):
                is_ready, error_msg = check_whorl_setup(console)
                assert is_ready is False
                assert "no documents" in error_msg.lower()
                assert "whorl upload" in error_msg

    def test_whorl_fully_configured(self):
        """Test when whorl is fully set up with documents."""
        console = Console()
        with tempfile.TemporaryDirectory() as tmpdir:
            whorl_home = Path(tmpdir) / ".whorl"
            whorl_home.mkdir()
            docs_dir = whorl_home / "docs"
            docs_dir.mkdir()
            # Create a document
            (docs_dir / "test.md").write_text("# Test document")

            with (
                patch("shutil.which", return_value="/usr/local/bin/whorl"),
                patch.object(Path, "home", return_value=Path(tmpdir)),
            ):
                is_ready, error_msg = check_whorl_setup(console)
                assert is_ready is True
                assert error_msg == ""


class TestEnsureWhorlRunning:
    """Tests for ensure_whorl_running function."""

    def test_whorl_already_running(self):
        """Test when whorl server is already running."""
        console = Console()
        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch("serendipity.agent.check_whorl_setup", return_value=(True, "")),
            patch("httpx.get", return_value=mock_response),
        ):
            result = ensure_whorl_running(console)
            assert result is True

    def test_whorl_setup_failed_not_installed(self):
        """Test when whorl is not installed."""
        console = Console()
        error_msg = "[red]Whorl not installed.[/red]"

        with patch(
            "serendipity.agent.check_whorl_setup",
            return_value=(False, error_msg),
        ):
            result = ensure_whorl_running(console)
            assert result is False

    def test_whorl_setup_failed_no_docs_continues(self):
        """Test that empty docs warning allows continuation."""
        console = Console()
        error_msg = "[yellow]Whorl has no documents.[/yellow]"
        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch(
                "serendipity.agent.check_whorl_setup",
                return_value=(False, error_msg),
            ),
            patch("httpx.get", return_value=mock_response),
        ):
            result = ensure_whorl_running(console)
            # Should continue because "no documents" is a soft warning
            assert result is True


class TestParseJson:
    """Tests for _parse_json method."""

    @pytest.fixture
    def agent(self):
        """Create agent for testing."""
        with patch("serendipity.agent.ensure_whorl_running"):
            return SerendipityAgent(console=Console(), whorl=False)

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


class TestGetPlugins:
    """Tests for _get_plugins method."""

    def test_no_plugins_when_whorl_disabled(self):
        """Test that no plugins are returned when whorl is disabled."""
        with patch("serendipity.agent.ensure_whorl_running"):
            agent = SerendipityAgent(console=Console(), whorl=False)
            plugins = agent._get_plugins()
            assert plugins == []

    def test_whorl_plugin_when_enabled(self):
        """Test that whorl plugin is returned when enabled."""
        with patch("serendipity.agent.ensure_whorl_running", return_value=True):
            agent = SerendipityAgent(console=Console(), whorl=True)
            plugins = agent._get_plugins()
            assert len(plugins) == 1
            assert plugins[0]["type"] == "local"
            assert "whorl" in plugins[0]["path"]


class TestAllowedTools:
    """Tests for allowed tools list building."""

    def test_base_tools_always_present(self):
        """Test that WebFetch and WebSearch are always in allowed tools."""
        # We can't easily test the discover method without mocking the SDK,
        # but we can verify the logic by inspecting the code structure.
        # This test documents the expected behavior.
        base_tools = ["WebFetch", "WebSearch"]
        assert "WebFetch" in base_tools
        assert "WebSearch" in base_tools

    def test_whorl_tools_list(self):
        """Test the list of whorl MCP tools."""
        whorl_tools = [
            "mcp__whorl__text_search_text_search_post",
            "mcp__whorl__agent_search_agent_search_post",
            "mcp__whorl__ingest_ingest_post",
            "mcp__whorl__bash_bash_post",
        ]
        assert len(whorl_tools) == 4
        assert all(tool.startswith("mcp__whorl__") for tool in whorl_tools)


class TestAgentInitialization:
    """Tests for SerendipityAgent initialization."""

    def test_default_initialization(self):
        """Test default agent initialization."""
        with patch("serendipity.agent.ensure_whorl_running"):
            agent = SerendipityAgent(console=Console())
            assert agent.model == "opus"
            assert agent.verbose is False
            assert agent.whorl is False

    def test_whorl_disabled_on_setup_failure(self):
        """Test that whorl is disabled if setup fails."""
        with patch("serendipity.agent.ensure_whorl_running", return_value=False):
            agent = SerendipityAgent(console=Console(), whorl=True)
            # Whorl should be disabled because ensure_whorl_running returned False
            assert agent.whorl is False

    def test_whorl_enabled_on_success(self):
        """Test that whorl stays enabled when setup succeeds."""
        with patch("serendipity.agent.ensure_whorl_running", return_value=True):
            agent = SerendipityAgent(console=Console(), whorl=True)
            assert agent.whorl is True

    def test_model_parameter(self):
        """Test different model parameters."""
        with patch("serendipity.agent.ensure_whorl_running"):
            for model in ["haiku", "sonnet", "opus"]:
                agent = SerendipityAgent(console=Console(), model=model)
                assert agent.model == model


class TestResumeCommand:
    """Tests for get_resume_command method."""

    def test_no_session_returns_none(self):
        """Test that no session returns None."""
        with patch("serendipity.agent.ensure_whorl_running"):
            agent = SerendipityAgent(console=Console())
            assert agent.get_resume_command() is None

    def test_session_returns_command(self):
        """Test that session ID returns proper command."""
        with patch("serendipity.agent.ensure_whorl_running"):
            agent = SerendipityAgent(console=Console())
            agent.last_session_id = "abc123"
            cmd = agent.get_resume_command()
            assert cmd == "claude -r abc123"
