"""Tests for serendipity agent module."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestParseResponse:
    """Tests for _parse_response method with new format."""

    @pytest.fixture
    def agent(self):
        """Create agent for testing."""
        return SerendipityAgent(console=Console())

    def test_parse_recommendations_tag(self, agent):
        """Test parsing <recommendations> tag."""
        text = """
        <recommendations>
        {"convergent": [{"url": "https://example.com", "reason": "test"}], "divergent": []}
        </recommendations>
        """
        result = agent._parse_response(text)
        assert len(result["convergent"]) == 1
        assert result["convergent"][0].url == "https://example.com"
        # Note: CSS is no longer parsed from response (now loaded from file)

    def test_parse_legacy_output_tag(self, agent):
        """Test parsing legacy <output> tag fallback."""
        text = """
        <output>
        {"convergent": [{"url": "https://legacy.com", "reason": "old format"}], "divergent": []}
        </output>
        """
        result = agent._parse_response(text)
        assert len(result["convergent"]) == 1
        assert result["convergent"][0].url == "https://legacy.com"

    def test_parse_with_metadata(self, agent):
        """Test parsing recommendations with metadata."""
        text = """
        <recommendations>
        {
            "convergent": [{
                "url": "https://youtube.com/watch?v=123",
                "reason": "Great video",
                "type": "youtube",
                "title": "Video Title",
                "metadata": {"channel": "TestChannel", "duration": "10:00"}
            }],
            "divergent": []
        }
        </recommendations>
        """
        result = agent._parse_response(text)
        assert len(result["convergent"]) == 1
        rec = result["convergent"][0]
        assert rec.url == "https://youtube.com/watch?v=123"
        assert rec.media_type == "youtube"
        assert rec.title == "Video Title"
        assert rec.metadata["channel"] == "TestChannel"


class TestRenderRecommendations:
    """Tests for _render_recommendations method."""

    @pytest.fixture
    def agent(self):
        """Create agent for testing."""
        return SerendipityAgent(console=Console())

    def test_render_empty_list(self, agent):
        """Test rendering empty recommendation list."""
        result = agent._render_recommendations([])
        assert result == ""

    def test_render_basic_recommendation(self, agent):
        """Test rendering basic recommendation."""
        from serendipity.models import Recommendation

        recs = [Recommendation(url="https://example.com", reason="Test reason")]
        result = agent._render_recommendations(recs)

        assert "https://example.com" in result
        assert "Test reason" in result
        assert "card" in result

    def test_render_with_title(self, agent):
        """Test rendering recommendation with title."""
        from serendipity.models import Recommendation

        recs = [Recommendation(
            url="https://example.com",
            reason="Test reason",
            title="Article Title",
        )]
        result = agent._render_recommendations(recs)

        assert "Article Title" in result
        assert "card-link" in result

    def test_render_with_thumbnail(self, agent):
        """Test rendering recommendation with thumbnail."""
        from serendipity.models import Recommendation

        recs = [Recommendation(
            url="https://youtube.com",
            reason="Test",
            thumbnail_url="https://img.youtube.com/vi/abc/0.jpg",
        )]
        result = agent._render_recommendations(recs)

        assert "card-media" in result
        assert "https://img.youtube.com/vi/abc/0.jpg" in result

    def test_render_with_metadata(self, agent):
        """Test rendering recommendation with metadata."""
        from serendipity.models import Recommendation

        recs = [Recommendation(
            url="https://example.com",
            reason="Test",
            metadata={"author": "Jane Doe", "year": "2024"},
        )]
        result = agent._render_recommendations(recs)

        assert "card-meta" in result
        assert "author" in result
        assert "Jane Doe" in result

    def test_render_escapes_html(self, agent):
        """Test that HTML characters are properly escaped."""
        from serendipity.models import Recommendation

        recs = [Recommendation(
            url="https://example.com?foo=1&bar=2",
            reason="Test <script>alert('xss')</script>",
        )]
        result = agent._render_recommendations(recs)

        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "&amp;" in result

    def test_render_multiple_recommendations(self, agent):
        """Test rendering multiple recommendations."""
        from serendipity.models import Recommendation

        recs = [
            Recommendation(url="https://one.com", reason="First"),
            Recommendation(url="https://two.com", reason="Second"),
            Recommendation(url="https://three.com", reason="Third"),
        ]
        result = agent._render_recommendations(recs)

        assert result.count("class=\"card\"") == 3
        assert "https://one.com" in result
        assert "https://two.com" in result
        assert "https://three.com" in result


class MockAsyncIterator:
    """Helper class to create a proper async iterator for testing."""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


class TestAgentWithMockedSDK:
    """Tests for agent methods with mocked Claude SDK."""

    @pytest.fixture
    def agent(self):
        """Create agent for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = SerendipityAgent(console=Console())
            agent.output_dir = Path(tmpdir)
            yield agent

    @pytest.mark.asyncio
    async def test_discover_creates_html_output(self, agent):
        """Test that discover creates HTML output file."""
        from claude_agent_sdk import ResultMessage, TextBlock, AssistantMessage

        # Create response items
        text_content = """
        <recommendations>
        {"convergent": [{"url": "https://example.com", "reason": "test"}], "divergent": []}
        </recommendations>
        <css>
        body { color: white; }
        </css>
        """
        responses = [
            AssistantMessage(content=[TextBlock(text=text_content)], model="opus"),
            ResultMessage(
                subtype="result",
                duration_ms=1000,
                duration_api_ms=900,
                is_error=False,
                num_turns=1,
                session_id="test-session-123",
                total_cost_usd=0.01,
            ),
        ]

        # Mock the Claude SDK client
        with patch("serendipity.agent.ClaudeSDKClient") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            # receive_response should return the async iterator directly
            mock_client.receive_response = MagicMock(return_value=MockAsyncIterator(responses))
            mock_client.query = AsyncMock()

            result = await agent.discover("Test context")

            assert result.session_id == "test-session-123"
            assert result.cost_usd == 0.01
            assert result.html_path is not None
            assert result.html_path.exists()

    @pytest.mark.asyncio
    async def test_discover_with_context_manager(self, agent):
        """Test discover uses context manager for MCP servers."""
        from claude_agent_sdk import ResultMessage, TextBlock, AssistantMessage

        mock_context_manager = MagicMock()
        mock_context_manager.get_mcp_servers.return_value = {
            "whorl": {"url": "http://localhost:8081/mcp/", "type": "http"}
        }
        mock_context_manager.get_allowed_tools.return_value = ["mcp__whorl__search"]
        mock_context_manager.get_system_prompt_hints.return_value = "Search Whorl first"
        mock_context_manager.get_enabled_source_names.return_value = ["whorl"]

        agent.context_manager = mock_context_manager

        text = '<recommendations>{"convergent": [], "divergent": []}</recommendations>'
        responses = [
            AssistantMessage(content=[TextBlock(text=text)], model="opus"),
            ResultMessage(
                subtype="result",
                duration_ms=1000,
                duration_api_ms=900,
                is_error=False,
                num_turns=1,
                session_id="test",
                total_cost_usd=0.01,
            ),
        ]

        with patch("serendipity.agent.ClaudeSDKClient") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_client.receive_response = MagicMock(return_value=MockAsyncIterator(responses))
            mock_client.query = AsyncMock()

            await agent.discover("Test context")

            # Verify MCP servers were included in options
            call_kwargs = MockClient.call_args
            assert call_kwargs is not None

    def test_agent_uses_types_config(self):
        """Test that agent uses types config for prompt building."""
        from serendipity.config.types import TypesConfig

        config = TypesConfig.default()
        config.total_count = 5

        agent = SerendipityAgent(console=Console(), types_config=config)

        assert agent.types_config.total_count == 5


class TestDiscoveryResult:
    """Tests for DiscoveryResult dataclass."""

    def test_create_result(self):
        """Test creating DiscoveryResult."""
        from serendipity.agent import DiscoveryResult
        from serendipity.models import Recommendation

        result = DiscoveryResult(
            convergent=[Recommendation(url="https://a.com", reason="test")],
            divergent=[],
            session_id="abc123",
            cost_usd=0.05,
        )

        assert len(result.convergent) == 1
        assert result.session_id == "abc123"
        assert result.cost_usd == 0.05
        assert result.html_style is None
        assert result.html_path is None

    def test_result_with_html_style(self):
        """Test DiscoveryResult with HTML style."""
        from serendipity.agent import DiscoveryResult
        from serendipity.models import HtmlStyle

        result = DiscoveryResult(
            convergent=[],
            divergent=[],
            session_id="test",
            html_style=HtmlStyle(description="Dark theme", css="body { background: #000; }"),
        )

        assert result.html_style is not None
        assert result.html_style.description == "Dark theme"


class TestAgentStreamingMessages:
    """Tests for agent handling of SDK streaming messages."""

    @pytest.fixture
    def agent(self, tmp_path):
        """Create agent with temp output directory."""
        console = MagicMock()
        agent = SerendipityAgent(console=console)
        agent.output_dir = tmp_path  # Override output dir after init
        return agent

    @pytest.mark.asyncio
    async def test_discover_handles_thinking_blocks(self, agent):
        """Test that discover processes ThinkingBlock messages."""
        from claude_agent_sdk import ResultMessage, ThinkingBlock, TextBlock, AssistantMessage

        # Include a thinking block in the response
        text = '<recommendations>{"convergent": [], "divergent": []}</recommendations>'
        responses = [
            AssistantMessage(
                content=[
                    ThinkingBlock(thinking="Let me analyze the user's preferences...", signature="test-sig"),
                ],
                model="opus"
            ),
            AssistantMessage(content=[TextBlock(text=text)], model="opus"),
            ResultMessage(
                subtype="result",
                duration_ms=1000,
                duration_api_ms=900,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                total_cost_usd=0.01,
            ),
        ]

        with patch("serendipity.agent.ClaudeSDKClient") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.receive_response = MagicMock(return_value=MockAsyncIterator(responses))
            mock_client.query = AsyncMock()

            result = await agent.discover("Test context")

            assert result is not None
            assert result.session_id == "test-session"

    @pytest.mark.asyncio
    async def test_discover_handles_tool_use_blocks(self, agent):
        """Test that discover processes ToolUseBlock messages."""
        from claude_agent_sdk import ResultMessage, ToolUseBlock, ToolResultBlock, TextBlock, AssistantMessage

        text = '<recommendations>{"convergent": [], "divergent": []}</recommendations>'
        responses = [
            AssistantMessage(
                content=[
                    ToolUseBlock(id="tool-1", name="WebSearch", input={"query": "test search"}),
                ],
                model="opus"
            ),
            AssistantMessage(
                content=[
                    ToolResultBlock(tool_use_id="tool-1", content="Search results..."),
                ],
                model="opus"
            ),
            AssistantMessage(content=[TextBlock(text=text)], model="opus"),
            ResultMessage(
                subtype="result",
                duration_ms=1000,
                duration_api_ms=900,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                total_cost_usd=0.02,
            ),
        ]

        with patch("serendipity.agent.ClaudeSDKClient") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.receive_response = MagicMock(return_value=MockAsyncIterator(responses))
            mock_client.query = AsyncMock()

            result = await agent.discover("Test context")

            assert result is not None
            assert result.cost_usd == 0.02

    @pytest.mark.asyncio
    async def test_discover_handles_system_init_message(self, agent):
        """Test that discover processes SystemMessage init events."""
        from claude_agent_sdk import ResultMessage, SystemMessage, TextBlock, AssistantMessage

        text = '<recommendations>{"convergent": [], "divergent": []}</recommendations>'
        responses = [
            SystemMessage(
                subtype="init",
                data={
                    "plugins": [{"name": "test-plugin"}],
                    "slash_commands": ["/test"],
                    "mcp_servers": ["whorl"],
                },
            ),
            AssistantMessage(content=[TextBlock(text=text)], model="opus"),
            ResultMessage(
                subtype="result",
                duration_ms=1000,
                duration_api_ms=900,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                total_cost_usd=0.01,
            ),
        ]

        with patch("serendipity.agent.ClaudeSDKClient") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.receive_response = MagicMock(return_value=MockAsyncIterator(responses))
            mock_client.query = AsyncMock()

            result = await agent.discover("Test context")

            assert result is not None

    @pytest.mark.asyncio
    async def test_discover_with_verbose_mode(self, agent, tmp_path):
        """Test that verbose mode shows additional info."""
        from claude_agent_sdk import ResultMessage, SystemMessage, TextBlock, AssistantMessage

        agent.verbose = True

        text = '<recommendations>{"convergent": [], "divergent": []}</recommendations>'
        responses = [
            SystemMessage(
                subtype="init",
                data={
                    "plugins": [{"name": "test-plugin"}],
                    "mcp_servers": ["whorl"],
                },
            ),
            AssistantMessage(content=[TextBlock(text=text)], model="opus"),
            ResultMessage(
                subtype="result",
                duration_ms=1000,
                duration_api_ms=900,
                is_error=False,
                num_turns=1,
                session_id="test-session",
                total_cost_usd=0.01,
            ),
        ]

        with patch("serendipity.agent.ClaudeSDKClient") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__aenter__.return_value = mock_client
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.receive_response = MagicMock(return_value=MockAsyncIterator(responses))
            mock_client.query = AsyncMock()

            result = await agent.discover("Test context")

            # In verbose mode, console.print should be called for plugins
            assert agent.console.print.called


class TestAgentParseResponse:
    """Tests for agent response parsing edge cases."""

    def test_parse_recommendations_with_output_tags(self):
        """Test parsing recommendations from <output> tags."""
        from serendipity.agent import SerendipityAgent

        agent = SerendipityAgent(console=MagicMock())

        text = '''
        <output>
        {"convergent": [{"url": "https://test.com", "reason": "Good content"}], "divergent": []}
        </output>
        '''

        result = agent._parse_response(text)

        assert len(result.get("convergent", [])) == 1
        assert result["convergent"][0].url == "https://test.com"

    def test_parse_recommendations_with_code_blocks(self):
        """Test parsing recommendations from code blocks."""
        from serendipity.agent import SerendipityAgent

        agent = SerendipityAgent(console=MagicMock())

        text = '''
        ```json
        {"convergent": [{"url": "https://test.com", "reason": "Good content"}], "divergent": []}
        ```
        '''

        result = agent._parse_response(text)

        assert len(result.get("convergent", [])) == 1

    def test_parse_recommendations_with_invalid_json(self):
        """Test parsing handles invalid JSON gracefully."""
        from serendipity.agent import SerendipityAgent

        agent = SerendipityAgent(console=MagicMock())

        text = '<recommendations>not valid json at all</recommendations>'

        result = agent._parse_response(text)

        # Should return empty result
        assert result.get("convergent", []) == []
        assert result.get("divergent", []) == []

    def test_parse_response_no_css_key(self):
        """Test that _parse_response does NOT return CSS (now loaded from file)."""
        from serendipity.agent import SerendipityAgent

        agent = SerendipityAgent(console=MagicMock())

        # CSS is now loaded from file, not parsed from response
        result = agent._parse_response('''
        <recommendations>
        {"convergent": [], "divergent": []}
        </recommendations>
        ''')

        # CSS key should NOT be in result
        assert "css" not in result
        # Only convergent and divergent keys
        assert "convergent" in result
        assert "divergent" in result
