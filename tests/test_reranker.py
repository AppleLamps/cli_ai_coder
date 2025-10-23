"""Tests for reranker functionality."""

import pytest
from indexer.rerank import BM25Reranker, CrossEncoderReranker, HybridReranker, Snippet


class TestBM25Reranker:
    """Test BM25 reranker."""

    def test_bm25_reranker(self):
        """Test basic BM25 reranking."""
        reranker = BM25Reranker()

        # Create test snippets
        candidates = [
            Snippet(path="file1.py", start_line=1, end_line=5, text="def hello world function", score=0.8),
            Snippet(path="file2.py", start_line=1, end_line=5, text="hello world greeting function", score=0.7),
            Snippet(path="file3.py", start_line=1, end_line=5, text="unrelated content here", score=0.6),
        ]

        query = "hello world function"
        results = reranker.rerank(query, candidates)

        # Should have rerank_score set
        assert all(hasattr(r, 'rerank_score') for r in results)
        assert results[0].rerank_score >= results[1].rerank_score  # Better match first

    def test_bm25_empty_candidates(self):
        """Test BM25 with empty candidates."""
        reranker = BM25Reranker()
        results = reranker.rerank("query", [])
        assert results == []


class TestCrossEncoderReranker:
    """Test cross-encoder reranker."""

    def test_cross_encoder_fallback(self):
        """Test cross-encoder fallback when model not available."""
        reranker = CrossEncoderReranker()

        # Model should be None if not available
        candidates = [
            Snippet(path="file1.py", start_line=1, end_line=5, text="test content", score=0.8),
        ]

        # Should not crash and return candidates with 0.0 rerank_score
        results = reranker.rerank("query", candidates)
        assert len(results) == 1
        assert results[0].rerank_score == 0.0


class TestHybridReranker:
    """Test hybrid reranker."""

    def test_bm25_fallback(self):
        """Test BM25 fallback."""
        reranker = HybridReranker("bm25")

        candidates = [
            Snippet(path="file1.py", start_line=1, end_line=5, text="def hello world", score=0.8),
            Snippet(path="file2.py", start_line=1, end_line=5, text="hello world function", score=0.7),
        ]

        results = reranker.rerank("hello world", candidates)
        assert len(results) == 2
        # BM25 scores can be negative, just check they're numbers
        assert all(isinstance(r.rerank_score, (int, float)) for r in results)

    def test_cross_encoder_fallback_to_bm25(self):
        """Test cross-encoder falling back to BM25."""
        reranker = HybridReranker("cross_encoder")

        candidates = [
            Snippet(path="file1.py", start_line=1, end_line=5, text="def hello world", score=0.8),
        ]

        results = reranker.rerank("hello world", candidates)
        # Should work even if cross-encoder not available (falls back to BM25)
        assert len(results) == 1
        # BM25 scores can be negative
        assert isinstance(results[0].rerank_score, (int, float))


class TestSnippet:
    """Test Snippet namedtuple."""

    def test_snippet_creation(self):
        """Test creating a Snippet."""
        snippet = Snippet(
            path="test.py",
            start_line=1,
            end_line=10,
            text="some code here",
            score=0.85,
            rerank_score=0.92
        )

        assert snippet.path == "test.py"
        assert snippet.start_line == 1
        assert snippet.end_line == 10
        assert snippet.text == "some code here"
        assert snippet.score == 0.85
        assert snippet.rerank_score == 0.92

    def test_snippet_default_rerank_score(self):
        """Test default rerank_score."""
        snippet = Snippet(
            path="test.py",
            start_line=1,
            end_line=10,
            text="some code here",
            score=0.85
        )

        assert snippet.rerank_score == 0.0