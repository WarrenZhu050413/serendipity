"""Tests for serendipity search module."""

import pytest

from serendipity.search import HistorySearcher
from serendipity.storage import HistoryEntry


def make_entry(url: str, reason: str, rating: int = 4, extracted: bool = False) -> HistoryEntry:
    """Helper to create test entries."""
    return HistoryEntry(
        url=url,
        reason=reason,
        type="convergent",
        rating=rating,
        timestamp="2024-01-15T10:30:00Z",
        session_id="abc123",
        extracted=extracted,
    )


class TestHistorySearcher:
    """Tests for HistorySearcher class."""

    def test_empty_entries(self):
        """Test with no entries."""
        searcher = HistorySearcher([])
        results = searcher.search("test")
        assert results == []

    def test_search_by_url(self):
        """Test searching by URL content."""
        entries = [
            make_entry("https://japanese-ceramics.com/gallery", "beautiful pottery"),
            make_entry("https://tech-news.com/article", "latest gadgets"),
            make_entry("https://japan-travel.com/kyoto", "travel guide"),
        ]
        searcher = HistorySearcher(entries)

        results = searcher.search("japanese")
        assert len(results) >= 1
        assert any("japanese" in r.url.lower() for r in results)

    def test_search_by_reason(self):
        """Test searching by reason content."""
        entries = [
            make_entry("https://example1.com", "minimalist design patterns"),
            make_entry("https://example2.com", "colorful abstract art"),
            make_entry("https://example3.com", "minimalist architecture"),
        ]
        searcher = HistorySearcher(entries)

        results = searcher.search("minimalist")
        assert len(results) == 2

    def test_search_multiple_terms(self):
        """Test searching with multiple terms."""
        entries = [
            make_entry("https://example1.com", "japanese minimalist design"),
            make_entry("https://example2.com", "japanese food recipes"),
            make_entry("https://example3.com", "minimalist living"),
            make_entry("https://example4.com", "unrelated content here"),  # Need 4+ for BM25
        ]
        searcher = HistorySearcher(entries)

        results = searcher.search("japanese minimalist")
        # Should rank entry with both terms higher
        assert len(results) >= 1
        # First result should be the one with both terms
        assert "japanese" in results[0].reason.lower() and "minimalist" in results[0].reason.lower()

    def test_search_no_matches(self):
        """Test searching with no matches."""
        entries = [
            make_entry("https://example1.com", "cooking recipes"),
            make_entry("https://example2.com", "travel guides"),
        ]
        searcher = HistorySearcher(entries)

        results = searcher.search("quantum physics")
        assert results == []

    def test_search_limit(self):
        """Test search result limiting."""
        entries = [make_entry(f"https://example{i}.com", "test content") for i in range(20)]
        searcher = HistorySearcher(entries)

        results = searcher.search("test", limit=5)
        assert len(results) <= 5

    def test_search_empty_query(self):
        """Test searching with empty query returns all entries."""
        entries = [
            make_entry("https://example1.com", "test1"),
            make_entry("https://example2.com", "test2"),
            make_entry("https://example3.com", "test3"),
        ]
        searcher = HistorySearcher(entries)

        results = searcher.search("", limit=10)
        assert len(results) == 3

    def test_filter_by_feedback(self):
        """Test filtering by feedback type (uses rating >= 4 for liked, <= 2 for disliked)."""
        entries = [
            make_entry("https://liked1.com", "liked content 1", rating=4),
            make_entry("https://disliked1.com", "disliked content", rating=2),
            make_entry("https://liked2.com", "liked content 2", rating=5),
        ]
        searcher = HistorySearcher(entries)

        liked_searcher = searcher.filter_by_feedback("liked")
        assert len(liked_searcher.entries) == 2

        disliked_searcher = searcher.filter_by_feedback("disliked")
        assert len(disliked_searcher.entries) == 1

    def test_filter_unextracted(self):
        """Test filtering to unextracted entries only."""
        entries = [
            make_entry("https://extracted.com", "extracted", extracted=True),
            make_entry("https://unextracted1.com", "unextracted 1", extracted=False),
            make_entry("https://unextracted2.com", "unextracted 2", extracted=False),
        ]
        searcher = HistorySearcher(entries)

        unextracted = searcher.filter_unextracted()
        assert len(unextracted.entries) == 2
        assert all(not e.extracted for e in unextracted.entries)

    def test_chained_filters(self):
        """Test chaining multiple filters."""
        entries = [
            make_entry("https://liked-extracted.com", "liked extracted", rating=4, extracted=True),
            make_entry("https://liked-unextracted.com", "liked unextracted", rating=5, extracted=False),
            make_entry("https://disliked-unextracted.com", "disliked", rating=2, extracted=False),
        ]
        searcher = HistorySearcher(entries)

        # Filter to liked AND unextracted
        filtered = searcher.filter_by_feedback("liked").filter_unextracted()
        assert len(filtered.entries) == 1
        assert filtered.entries[0].url == "https://liked-unextracted.com"

    def test_search_on_filtered(self):
        """Test searching on a filtered searcher."""
        entries = [
            make_entry("https://liked-japanese.com", "japanese minimalism", rating=4),
            make_entry("https://liked-tech.com", "tech news articles", rating=5),
            make_entry("https://liked-cooking.com", "french cooking tips", rating=4),
            make_entry("https://disliked-japanese.com", "japanese anime shows", rating=2),
        ]
        searcher = HistorySearcher(entries)

        liked_searcher = searcher.filter_by_feedback("liked")
        results = liked_searcher.search("japanese")
        assert len(results) == 1
        assert results[0].url == "https://liked-japanese.com"

    def test_tokenization(self):
        """Test that tokenization handles URLs properly."""
        entries = [
            make_entry("https://www.example-site.com/path/to/page", "content here"),
            make_entry("https://other-site.com", "different content"),
            make_entry("https://another.org", "more stuff"),
        ]
        searcher = HistorySearcher(entries)

        # Should match parts of URL
        results = searcher.search("example")
        assert len(results) == 1
        assert "example" in results[0].url

    def test_case_insensitive(self):
        """Test that search is case insensitive."""
        entries = [
            make_entry("https://example.com", "Japanese MINIMALISM Design"),
            make_entry("https://other.com", "french cooking style"),
            make_entry("https://third.com", "italian architecture"),
        ]
        searcher = HistorySearcher(entries)

        results = searcher.search("japanese")
        assert len(results) == 1
        assert "Japanese" in results[0].reason

        results = searcher.search("JAPANESE")
        assert len(results) == 1

        results = searcher.search("JaPaNeSe")
        assert len(results) == 1
