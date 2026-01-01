"""Tests for serendipity profile builder module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from rich.console import Console

from serendipity.profile_builder import (
    BuildSession,
    ProfileBuilder,
    QuestionOption,
    TasteQuestion,
    UserAnswer,
)


class TestDataClasses:
    """Tests for ProfileBuilder data classes."""

    def test_question_option_creation(self):
        """Test QuestionOption dataclass."""
        opt = QuestionOption(
            value="minimalist",
            label="Minimalism",
            description="Clean, sparse aesthetics",
            recommended=True,
        )
        assert opt.value == "minimalist"
        assert opt.label == "Minimalism"
        assert opt.description == "Clean, sparse aesthetics"
        assert opt.recommended is True

    def test_question_option_defaults(self):
        """Test QuestionOption default values."""
        opt = QuestionOption(
            value="test",
            label="Test",
            description="Test description",
        )
        assert opt.recommended is False

    def test_taste_question_creation(self):
        """Test TasteQuestion dataclass."""
        options = [
            QuestionOption(value="a", label="A", description="A desc"),
            QuestionOption(value="b", label="B", description="B desc"),
        ]
        q = TasteQuestion(
            id="visual_style",
            category="Aesthetics",
            question="What visual style resonates with you?",
            options=options,
            multi_select=True,
        )
        assert q.id == "visual_style"
        assert q.category == "Aesthetics"
        assert len(q.options) == 2
        assert q.multi_select is True

    def test_taste_question_defaults(self):
        """Test TasteQuestion default values."""
        q = TasteQuestion(
            id="test",
            category="Test",
            question="Test?",
            options=[],
        )
        assert q.multi_select is False

    def test_user_answer_creation(self):
        """Test UserAnswer dataclass."""
        answer = UserAnswer(
            question_id="visual_style",
            category="Aesthetics",
            question="What visual style?",
            selected=["Minimalism", "Industrial"],
            other="I also like brutalism",
        )
        assert answer.question_id == "visual_style"
        assert len(answer.selected) == 2
        assert answer.other == "I also like brutalism"

    def test_user_answer_defaults(self):
        """Test UserAnswer default values."""
        answer = UserAnswer(
            question_id="test",
            category="Test",
            question="Test?",
            selected=["A"],
        )
        assert answer.other == ""

    def test_build_session_creation(self):
        """Test BuildSession dataclass."""
        session = BuildSession(current_taste="My existing taste profile")
        assert session.current_taste == "My existing taste profile"
        assert len(session.asked_topics) == 0
        assert len(session.all_answers) == 0
        assert session.round_number == 1

    def test_build_session_track_topics(self):
        """Test BuildSession topic tracking."""
        session = BuildSession(current_taste="")
        session.asked_topics.add("visual_style")
        session.asked_topics.add("content_depth")
        assert "visual_style" in session.asked_topics
        assert "content_depth" in session.asked_topics
        assert len(session.asked_topics) == 2


class TestProfileBuilderParsing:
    """Tests for ProfileBuilder parsing methods."""

    @pytest.fixture
    def mock_storage(self, tmp_path):
        """Create a mock storage manager."""
        storage = MagicMock()
        storage.get_prompt_path = MagicMock(side_effect=self._mock_prompt_path(tmp_path))
        storage.load_taste = MagicMock(return_value="")
        storage.save_taste = MagicMock()
        storage.taste_path = tmp_path / "taste.md"
        return storage

    def _mock_prompt_path(self, tmp_path):
        """Create a mock for get_prompt_path that writes default content."""
        def mock_fn(name: str, default_content: str):
            path = tmp_path / "prompts" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default_content)
            return path
        return mock_fn

    @pytest.fixture
    def builder(self, mock_storage):
        """Create a ProfileBuilder instance with mocked dependencies."""
        return ProfileBuilder(
            console=Console(force_terminal=True, width=80),
            storage=mock_storage,
            model="opus",
            max_thinking_tokens=10000,
            verbose=False,
        )

    def test_parse_questions_valid_json(self, builder):
        """Test parsing valid questions JSON."""
        response = """
Some thinking here...

<questions>
[
  {
    "id": "visual_style",
    "category": "Aesthetics",
    "question": "What visual style resonates?",
    "multi_select": false,
    "options": [
      {"value": "minimalist", "label": "Minimalism", "description": "Clean and sparse", "recommended": true},
      {"value": "maximalist", "label": "Maximalism", "description": "Rich and layered", "recommended": false}
    ]
  }
]
</questions>
"""
        questions = builder._parse_questions(response)
        assert len(questions) == 1
        assert questions[0].id == "visual_style"
        assert questions[0].category == "Aesthetics"
        assert len(questions[0].options) == 2
        assert questions[0].options[0].recommended is True

    def test_parse_questions_multiple(self, builder):
        """Test parsing multiple questions."""
        response = """
<questions>
[
  {"id": "q1", "category": "A", "question": "Q1?", "options": [{"value": "a", "label": "A", "description": "A desc"}]},
  {"id": "q2", "category": "B", "question": "Q2?", "options": [{"value": "b", "label": "B", "description": "B desc"}]}
]
</questions>
"""
        questions = builder._parse_questions(response)
        assert len(questions) == 2
        assert questions[0].id == "q1"
        assert questions[1].id == "q2"

    def test_parse_questions_missing_tags(self, builder):
        """Test parsing questions without XML tags (raw JSON)."""
        response = """
[
  {"id": "test", "category": "Test", "question": "Test?", "options": [{"value": "x", "label": "X", "description": "X desc"}]}
]
"""
        questions = builder._parse_questions(response)
        assert len(questions) == 1
        assert questions[0].id == "test"

    def test_parse_questions_invalid_json(self, builder):
        """Test parsing invalid JSON returns empty list."""
        response = "Not valid JSON at all"
        questions = builder._parse_questions(response)
        assert len(questions) == 0

    def test_parse_profile_valid(self, builder):
        """Test parsing valid profile content."""
        response = """
Some synthesis thinking...

<taste_profile>
# My Taste

I love minimalism and clean design.
</taste_profile>
"""
        profile = builder._parse_profile(response)
        assert "# My Taste" in profile
        assert "I love minimalism" in profile

    def test_parse_profile_no_tags(self, builder):
        """Test parsing profile without XML tags returns full text."""
        response = "# My Taste\n\nI love minimalism."
        profile = builder._parse_profile(response)
        assert "# My Taste" in profile

    def test_format_answers_empty(self, builder):
        """Test formatting empty answers."""
        formatted = builder._format_answers([])
        assert formatted == ""

    def test_format_answers_with_content(self, builder):
        """Test formatting answers with content."""
        answers = [
            UserAnswer(
                question_id="q1",
                category="Aesthetics",
                question="What style?",
                selected=["Minimalism"],
                other="",
            ),
            UserAnswer(
                question_id="q2",
                category="Content",
                question="What depth?",
                selected=["Deep", "Playful"],
                other="Also concise",
            ),
        ]
        formatted = builder._format_answers(answers)
        assert "Aesthetics" in formatted
        assert "What style?" in formatted
        assert "Minimalism" in formatted
        assert "Deep, Playful" in formatted
        assert "Also concise" in formatted


class TestProfileBuilderCLI:
    """Tests for the profile build CLI command."""

    def test_profile_build_command_exists(self):
        """Test that profile build command is registered."""
        from typer.testing import CliRunner
        from serendipity.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["profile", "build", "--help"])
        assert result.exit_code == 0
        assert "Build or improve your taste profile" in result.stdout
        assert "--thinking" in result.stdout
        assert "--questions" in result.stdout
        assert "--options" in result.stdout
        assert "--reset" in result.stdout
        assert "--verbose" in result.stdout

    def test_profile_build_options(self):
        """Test that profile build has expected options."""
        from typer.testing import CliRunner
        from serendipity.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["profile", "build", "--help"])
        assert "-t" in result.stdout  # thinking shorthand
        assert "-v" in result.stdout  # verbose shorthand
        assert "-m" in result.stdout  # model shorthand


class TestProfileBuilderRevision:
    """Tests for ProfileBuilder revision and preview methods."""

    @pytest.fixture
    def mock_storage(self, tmp_path):
        """Create a mock storage manager."""
        storage = MagicMock()
        def mock_prompt_path(name: str, default_content: str):
            path = tmp_path / "prompts" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default_content)
            return path
        storage.get_prompt_path = MagicMock(side_effect=mock_prompt_path)
        storage.load_taste = MagicMock(return_value="")
        storage.save_taste = MagicMock()
        storage.taste_path = tmp_path / "taste.md"
        return storage

    @pytest.fixture
    def builder(self, mock_storage):
        """Create a ProfileBuilder instance with mocked dependencies."""
        return ProfileBuilder(
            console=Console(force_terminal=True, width=80),
            storage=mock_storage,
            model="opus",
            max_thinking_tokens=10000,
            verbose=False,
        )

    def test_revision_prompt_loaded(self, builder):
        """Test that revision prompt is loaded."""
        assert builder.revision_prompt is not None
        assert "{draft_profile}" in builder.revision_prompt
        assert "{feedback}" in builder.revision_prompt

    def test_preview_prompt_loaded(self, builder):
        """Test that preview prompt is loaded."""
        assert builder.preview_prompt is not None
        assert "{taste_profile}" in builder.preview_prompt

    @pytest.mark.asyncio
    async def test_revise_profile_parses_response(self, builder):
        """Test that revise_profile correctly parses the response."""
        async def mock_receive_response():
            # Yield nothing - empty async generator
            return
            yield  # Makes this an async generator

        with patch.object(builder, '_parse_profile', return_value="# Revised Profile\n\nUpdated based on feedback.") as mock_parse:
            with patch("serendipity.profile_builder.ClaudeSDKClient") as mock_client_cls:
                # Setup mock client
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__.return_value = mock_client
                mock_client.query = AsyncMock()
                mock_client.receive_response = mock_receive_response

                # Call revise_profile
                result = await builder.revise_profile("Original profile", "Make it shorter")

                # Verify _parse_profile was called
                mock_parse.assert_called_once()

    @pytest.mark.asyncio
    async def test_preview_recommendations_returns_text(self, builder):
        """Test that preview_recommendations returns recommendation text."""
        async def mock_receive_response():
            # Yield nothing - empty async generator
            return
            yield  # Makes this an async generator

        with patch("serendipity.profile_builder.ClaudeSDKClient") as mock_client_cls:
            # Setup mock client
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.query = AsyncMock()
            mock_client.receive_response = mock_receive_response

            # Call preview_recommendations
            result = await builder.preview_recommendations("My taste profile")

            # Should return a string (even if empty from mock)
            assert isinstance(result, str)


class TestBuildSessionState:
    """Tests for BuildSession state management."""

    def test_session_accumulates_answers(self):
        """Test that session accumulates answers across rounds."""
        session = BuildSession(current_taste="Initial taste")

        # Round 1
        session.all_answers.append(
            UserAnswer(question_id="q1", category="A", question="Q1?", selected=["A"])
        )
        session.asked_topics.add("q1")
        session.round_number = 2

        # Round 2
        session.all_answers.append(
            UserAnswer(question_id="q2", category="B", question="Q2?", selected=["B"])
        )
        session.asked_topics.add("q2")

        assert len(session.all_answers) == 2
        assert len(session.asked_topics) == 2
        assert session.round_number == 2

    def test_session_tracks_asked_topics(self):
        """Test that asked topics prevent duplicates."""
        session = BuildSession(current_taste="")

        session.asked_topics.add("visual_style")
        session.asked_topics.add("content_depth")
        session.asked_topics.add("visual_style")  # Duplicate

        assert len(session.asked_topics) == 2
