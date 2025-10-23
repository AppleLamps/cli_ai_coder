"""Hybrid reranker for search results."""

import logging
from typing import List, Optional, NamedTuple
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Snippet(NamedTuple):
    """A search result snippet with reranking score."""
    path: str
    start_line: int
    end_line: int
    text: str
    score: float
    rerank_score: float = 0.0


class Reranker(ABC):
    """Abstract base class for rerankers."""

    @abstractmethod
    def rerank(self, query: str, candidates: List[Snippet]) -> List[Snippet]:
        """
        Rerank candidates based on query relevance.

        Args:
            query: Search query string
            candidates: List of Snippet objects to rerank

        Returns:
            Reranked list of snippets with rerank_score field updated
        """
        pass


class BM25Reranker(Reranker):
    """BM25-based reranker using pure Python implementation."""

    def __init__(self):
        self.k1 = 1.5  # BM25 parameter
        self.b = 0.75  # BM25 parameter

    def rerank(self, query: str, candidates: List[Snippet]) -> List[Snippet]:
        """Rerank using BM25 scoring."""
        if not candidates:
            return candidates

        # Tokenize query
        query_terms = self._tokenize(query)

        # Calculate document lengths and average length
        doc_lengths = [len(self._tokenize(snippet.text)) for snippet in candidates]
        avg_doc_length = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 1

        # Build term frequency and document frequency
        term_df = {}  # term -> number of docs containing term
        for snippet in candidates:
            doc_terms = set(self._tokenize(snippet.text))
            for term in doc_terms:
                term_df[term] = term_df.get(term, 0) + 1

        # Score each document
        scored_candidates = []
        for snippet, doc_length in zip(candidates, doc_lengths):
            score = 0.0
            doc_terms = self._tokenize(snippet.text)
            term_freq = {}
            for term in doc_terms:
                term_freq[term] = term_freq.get(term, 0) + 1

            for term in query_terms:
                if term in term_freq:
                    # BM25 scoring formula
                    tf = term_freq[term]
                    df = term_df.get(term, 0)
                    idf = self._idf(len(candidates), df)

                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (1 - self.b + self.b * (doc_length / avg_doc_length))
                    score += idf * (numerator / denominator)

            # Add score to snippet
            scored_snippet = snippet._replace(rerank_score=score)
            scored_candidates.append(scored_snippet)

        # Sort by score descending
        scored_candidates.sort(key=lambda x: x.rerank_score, reverse=True)
        return scored_candidates

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        import re
        # Split on whitespace and punctuation, convert to lowercase
        return re.findall(r'\b\w+\b', text.lower())

    def _idf(self, total_docs: int, doc_freq: int) -> float:
        """Calculate inverse document frequency."""
        import math
        if doc_freq == 0:
            return 0.0
        return math.log((total_docs - doc_freq + 0.5) / (doc_freq + 0.5))


class CrossEncoderReranker(Reranker):
    """Cross-encoder based reranker using sentence-transformers."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self.model = None
        self._load_model()

    def _load_model(self):
        """Lazy load the cross-encoder model."""
        if self.model is None:
            try:
                from sentence_transformers import CrossEncoder
                self.model = CrossEncoder(self.model_name)
                logger.info(f"Loaded cross-encoder model: {self.model_name}")
            except ImportError:
                logger.warning("sentence-transformers not available for cross-encoder")
                self.model = None
            except Exception as e:
                logger.warning(f"Failed to load cross-encoder model: {e}")
                self.model = None

    def rerank(self, query: str, candidates: List[Snippet]) -> List[Snippet]:
        """Rerank using cross-encoder scoring."""
        if not candidates or self.model is None:
            # Fallback to no-op if model not available
            return [snippet._replace(rerank_score=0.0) for snippet in candidates]

        # Prepare input pairs
        query_doc_pairs = [[query, snippet.text] for snippet in candidates]

        try:
            # Get scores from cross-encoder
            scores = self.model.predict(query_doc_pairs)

            # Add scores to snippets
            scored_candidates = []
            for snippet, score in zip(candidates, scores):
                scored_snippet = snippet._replace(rerank_score=float(score))
                scored_candidates.append(scored_snippet)

            # Sort by score descending
            scored_candidates.sort(key=lambda x: x.rerank_score, reverse=True)
            return scored_candidates

        except Exception as e:
            logger.warning(f"Cross-encoder prediction failed: {e}")
            # Fallback to no-op
            return [snippet._replace(rerank_score=0.0) for snippet in candidates]


class HybridReranker:
    """Hybrid reranker that tries cross-encoder first, falls back to BM25."""

    def __init__(self, reranker_type: str = "bm25", cross_encoder_model: Optional[str] = None):
        self.reranker_type = reranker_type
        self.cross_encoder_model = cross_encoder_model or "cross-encoder/ms-marco-MiniLM-L-6-v2"

        self._reranker = None

    def rerank(self, query: str, candidates: List[Snippet]) -> List[Snippet]:
        """Rerank candidates using the configured reranker."""
        if self._reranker is None:
            self._reranker = self._create_reranker()

        return self._reranker.rerank(query, candidates)

    def _create_reranker(self) -> Reranker:
        """Create the appropriate reranker based on configuration."""
        if self.reranker_type == "cross_encoder":
            reranker = CrossEncoderReranker(self.cross_encoder_model)
            # Test if model loaded successfully
            if reranker.model is None:
                logger.info("Cross-encoder not available, falling back to BM25")
                return BM25Reranker()
            return reranker
        else:
            # Default to BM25
            return BM25Reranker()


# Global reranker instance
_reranker: Optional[HybridReranker] = None


def get_reranker(reranker_type: str = "bm25", cross_encoder_model: Optional[str] = None) -> HybridReranker:
    """Get or create the global reranker instance."""
    global _reranker
    if _reranker is None or _reranker.reranker_type != reranker_type:
        _reranker = HybridReranker(reranker_type, cross_encoder_model)
    return _reranker