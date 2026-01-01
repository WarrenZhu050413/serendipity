"""Tests for the learnings parser module."""

import pytest
from serendipity.learnings_parser import (
    Learning,
    _generate_id,
    add_learning,
    delete_learning_by_id,
    find_learning_by_id,
    parse_learnings,
    serialize_learnings,
    update_learning_by_id,
)


class TestGenerateId:
    """Tests for ID generation."""

    def test_generates_8_char_id(self):
        """ID should be 8 characters."""
        id_ = _generate_id("title", "content")
        assert len(id_) == 8

    def test_same_input_same_id(self):
        """Same title+content should generate same ID."""
        id1 = _generate_id("title", "content")
        id2 = _generate_id("title", "content")
        assert id1 == id2

    def test_different_input_different_id(self):
        """Different content should generate different IDs."""
        id1 = _generate_id("title", "content1")
        id2 = _generate_id("title", "content2")
        assert id1 != id2


class TestParseLearnings:
    """Tests for parsing learnings markdown."""

    def test_parse_empty_string(self):
        """Empty string should return empty list."""
        result = parse_learnings("")
        assert result == []

    def test_parse_whitespace_only(self):
        """Whitespace only should return empty list."""
        result = parse_learnings("   \n\n  ")
        assert result == []

    def test_parse_single_like(self):
        """Should parse a single like entry."""
        markdown = """# My Discovery Learnings

## Likes

### Prefers long essays
I like reading long-form content over quick summaries.
"""
        result = parse_learnings(markdown)
        assert len(result) == 1
        assert result[0].learning_type == "like"
        assert result[0].title == "Prefers long essays"
        assert "long-form content" in result[0].content

    def test_parse_single_dislike(self):
        """Should parse a single dislike entry."""
        markdown = """# Learnings

## Dislikes

### Clickbait content
I don't enjoy sensationalized headlines.
"""
        result = parse_learnings(markdown)
        assert len(result) == 1
        assert result[0].learning_type == "dislike"
        assert result[0].title == "Clickbait content"

    def test_parse_multiple_entries(self):
        """Should parse multiple entries in both sections."""
        markdown = """# Learnings

## Likes

### Topic A
Content about A

### Topic B
Content about B

## Dislikes

### Topic C
Content about C
"""
        result = parse_learnings(markdown)
        assert len(result) == 3
        assert result[0].learning_type == "like"
        assert result[0].title == "Topic A"
        assert result[1].learning_type == "like"
        assert result[1].title == "Topic B"
        assert result[2].learning_type == "dislike"
        assert result[2].title == "Topic C"

    def test_parse_multiline_content(self):
        """Should handle multiline content."""
        markdown = """## Likes

### Complex topic
Line 1
Line 2
Line 3
"""
        result = parse_learnings(markdown)
        assert len(result) == 1
        assert "Line 1" in result[0].content
        assert "Line 2" in result[0].content
        assert "Line 3" in result[0].content


class TestSerializeLearnings:
    """Tests for serializing learnings back to markdown."""

    def test_serialize_empty_list(self):
        """Empty list should produce template structure."""
        result = serialize_learnings([])
        assert "# My Discovery Learnings" in result
        assert "## Likes" in result
        assert "## Dislikes" in result

    def test_serialize_single_like(self):
        """Should serialize a single like entry."""
        learnings = [
            Learning(
                id="abc12345",
                learning_type="like",
                title="Test Title",
                content="Test content here",
            )
        ]
        result = serialize_learnings(learnings)
        assert "### Test Title" in result
        assert "Test content here" in result
        assert "## Likes" in result

    def test_serialize_mixed(self):
        """Should serialize mixed likes and dislikes."""
        learnings = [
            Learning(id="a", learning_type="like", title="Like One", content="Like content"),
            Learning(id="b", learning_type="dislike", title="Dislike One", content="Dislike content"),
        ]
        result = serialize_learnings(learnings)
        assert "### Like One" in result
        assert "### Dislike One" in result
        # Likes should come before dislikes
        likes_pos = result.index("## Likes")
        dislikes_pos = result.index("## Dislikes")
        like_title_pos = result.index("Like One")
        dislike_title_pos = result.index("Dislike One")
        assert likes_pos < like_title_pos < dislikes_pos < dislike_title_pos


class TestRoundTrip:
    """Tests for parse/serialize roundtrip."""

    def test_roundtrip_preserves_content(self):
        """Parsing then serializing should preserve content."""
        original = """# My Discovery Learnings

## Likes

### Topic A
Content for topic A

### Topic B
Content for topic B

## Dislikes

### Topic C
Content for topic C
"""
        learnings = parse_learnings(original)
        serialized = serialize_learnings(learnings)
        reparsed = parse_learnings(serialized)

        assert len(reparsed) == len(learnings)
        for orig, new in zip(learnings, reparsed):
            assert orig.title == new.title
            assert orig.content.strip() == new.content.strip()
            assert orig.learning_type == new.learning_type


class TestFindLearningById:
    """Tests for finding learnings by ID."""

    def test_find_existing(self):
        """Should find existing learning."""
        learnings = [
            Learning(id="abc", learning_type="like", title="Test", content="Content"),
        ]
        result = find_learning_by_id(learnings, "abc")
        assert result is not None
        assert result.id == "abc"

    def test_find_not_existing(self):
        """Should return None for missing ID."""
        learnings = [
            Learning(id="abc", learning_type="like", title="Test", content="Content"),
        ]
        result = find_learning_by_id(learnings, "xyz")
        assert result is None

    def test_find_in_empty_list(self):
        """Should return None for empty list."""
        result = find_learning_by_id([], "abc")
        assert result is None


class TestDeleteLearningById:
    """Tests for deleting learnings by ID."""

    def test_delete_existing(self):
        """Should remove existing learning."""
        learnings = [
            Learning(id="abc", learning_type="like", title="Test1", content="Content1"),
            Learning(id="def", learning_type="like", title="Test2", content="Content2"),
        ]
        result = delete_learning_by_id(learnings, "abc")
        assert len(result) == 1
        assert result[0].id == "def"

    def test_delete_not_existing(self):
        """Should return unchanged list for missing ID."""
        learnings = [
            Learning(id="abc", learning_type="like", title="Test", content="Content"),
        ]
        result = delete_learning_by_id(learnings, "xyz")
        assert len(result) == 1
        assert result[0].id == "abc"


class TestUpdateLearningById:
    """Tests for updating learnings by ID."""

    def test_update_title(self):
        """Should update title and regenerate ID."""
        learnings = [
            Learning(id="old_id", learning_type="like", title="Old Title", content="Content"),
        ]
        result = update_learning_by_id(learnings, "old_id", title="New Title")
        assert len(result) == 1
        assert result[0].title == "New Title"
        # ID should change since content changed
        assert result[0].id != "old_id"

    def test_update_content(self):
        """Should update content and regenerate ID."""
        learnings = [
            Learning(id="old_id", learning_type="like", title="Title", content="Old Content"),
        ]
        result = update_learning_by_id(learnings, "old_id", content="New Content")
        assert len(result) == 1
        assert result[0].content == "New Content"

    def test_update_not_existing(self):
        """Should return unchanged list for missing ID."""
        learnings = [
            Learning(id="abc", learning_type="like", title="Title", content="Content"),
        ]
        result = update_learning_by_id(learnings, "xyz", title="New Title")
        assert len(result) == 1
        assert result[0].title == "Title"


class TestAddLearning:
    """Tests for adding new learnings."""

    def test_add_to_empty(self):
        """Should add to empty list."""
        result = add_learning([], "like", "New Title", "New Content")
        assert len(result) == 1
        assert result[0].title == "New Title"
        assert result[0].content == "New Content"
        assert result[0].learning_type == "like"

    def test_add_to_existing(self):
        """Should append to existing list."""
        learnings = [
            Learning(id="abc", learning_type="like", title="Existing", content="Content"),
        ]
        result = add_learning(learnings, "dislike", "New", "New content")
        assert len(result) == 2
        assert result[1].title == "New"
        assert result[1].learning_type == "dislike"

    def test_add_generates_id(self):
        """Should generate ID based on content."""
        result = add_learning([], "like", "Title", "Content")
        assert len(result[0].id) == 8


class TestLearningToDict:
    """Tests for Learning.to_dict()."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        learning = Learning(
            id="abc12345",
            learning_type="like",
            title="Test Title",
            content="Test content",
        )
        result = learning.to_dict()
        assert result == {
            "id": "abc12345",
            "type": "like",
            "title": "Test Title",
            "content": "Test content",
        }


class TestLearningFromDict:
    """Tests for Learning.from_dict()."""

    def test_from_dict(self):
        """Should create from dictionary."""
        data = {
            "id": "abc12345",
            "type": "dislike",
            "title": "Test Title",
            "content": "Test content",
        }
        result = Learning.from_dict(data)
        assert result.id == "abc12345"
        assert result.learning_type == "dislike"
        assert result.title == "Test Title"
        assert result.content == "Test content"

    def test_from_dict_with_defaults(self):
        """Should use defaults for missing fields."""
        data = {}
        result = Learning.from_dict(data)
        assert result.id == ""
        assert result.learning_type == "like"
        assert result.title == ""
        assert result.content == ""
