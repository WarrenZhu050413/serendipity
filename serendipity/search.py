"""BM25 search over history entries."""

import re

from rank_bm25 import BM25L

from serendipity.storage import HistoryEntry


def _tokenize_text(text: str) -> list[str]:
    """Tokenize text for BM25 indexing.

    Splits on whitespace and URL separators (/, -, ., _, :, ?).
    Filters out very short tokens (< 2 chars) and common URL parts.
    """
    # Split on common separators
    tokens = re.split(r'[\s/\-._:?&=]+', text.lower())
    # Filter out short tokens and common URL noise
    noise = {'http', 'https', 'www', 'com', 'org', 'net', 'html', 'htm'}
    return [t for t in tokens if len(t) >= 2 and t not in noise]


class HistorySearcher:
    """BM25 search over history entries."""

    def __init__(self, entries: list[HistoryEntry]):
        """Initialize searcher with history entries.

        Args:
            entries: List of history entries to index
        """
        self.entries = entries
        if entries:
            self.corpus = [self._tokenize(e) for e in entries]
            self.bm25 = BM25L(self.corpus)
        else:
            self.corpus = []
            self.bm25 = None

    def _tokenize(self, entry: HistoryEntry) -> list[str]:
        """Tokenize an entry for indexing.

        Indexes on: url, reason, type, feedback
        """
        text = f"{entry.url} {entry.reason} {entry.type}"
        if entry.feedback:
            text += f" {entry.feedback}"
        return _tokenize_text(text)

    def search(self, query: str, limit: int = 20) -> list[HistoryEntry]:
        """Search entries by query.

        Args:
            query: Search query (keywords)
            limit: Maximum results to return

        Returns:
            List of matching entries, ranked by relevance
        """
        if not self.entries or not self.bm25:
            return []

        tokens = _tokenize_text(query)
        if not tokens:
            return self.entries[:limit]

        scores = self.bm25.get_scores(tokens)
        ranked = sorted(zip(self.entries, scores), key=lambda x: -x[1])
        return [e for e, s in ranked[:limit] if s > 0]

    def filter_by_feedback(self, feedback: str) -> "HistorySearcher":
        """Create a new searcher filtered by feedback type.

        Args:
            feedback: "liked" or "disliked"

        Returns:
            New HistorySearcher with filtered entries
        """
        filtered = [e for e in self.entries if e.feedback == feedback]
        return HistorySearcher(filtered)

    def filter_unextracted(self) -> "HistorySearcher":
        """Create a new searcher with only unextracted entries.

        Returns:
            New HistorySearcher with unextracted entries only
        """
        filtered = [e for e in self.entries if not e.extracted]
        return HistorySearcher(filtered)
