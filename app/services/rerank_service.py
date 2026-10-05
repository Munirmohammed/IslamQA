"""
Cross-Encoder Reranking
Final re-scoring pass over the top-K fused (RRF) candidates using a
cross-encoder, which scores (query, document) pairs jointly rather than
comparing independently-computed embeddings — typically more accurate than
the bi-encoder/dense similarity used for first-stage retrieval, at the cost
of being too slow to run over the full corpus (hence: retrieve-then-rerank,
applied only to a small top-K).

No new dependency: sentence-transformers (already a project dependency for
the dense retrieval bi-encoder) ships CrossEncoder directly.
"""

from typing import Any, Dict, List

import structlog
from sentence_transformers import CrossEncoder

logger = structlog.get_logger()

# Small multilingual cross-encoder with Arabic coverage. Kept as a single
# constant (not settings-driven) since swapping it is a deliberate model
# choice, not a runtime config knob.
DEFAULT_RERANK_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

# This is a demo-scale project, not a production reranker — keep K small so
# a cross-encoder forward pass per candidate stays fast.
MAX_RERANK_CANDIDATES = 30


class CrossEncoderReranker:
    """Wraps a cross-encoder model for query/candidate reranking."""

    def __init__(self, model_name: str = DEFAULT_RERANK_MODEL):
        self.model_name = model_name
        self.model: CrossEncoder = None

    def load(self):
        """Load the cross-encoder model. Call once at service startup."""
        try:
            self.model = CrossEncoder(self.model_name)
            logger.info(f"Loaded cross-encoder reranker: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load cross-encoder reranker: {str(e)}")
            self.model = None

    def rerank(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Re-sort `results` (each expected to have a 'question' field) by
        cross-encoder relevance to `query`. Falls back to the original
        (fused-rank) order if the model isn't loaded or scoring fails —
        matching this codebase's existing fallback-on-error convention
        (e.g. VectorEmbeddings.find_similar_questions -> _fallback_similarity_search).
        """
        if not results:
            return results

        if self.model is None:
            logger.warning("Cross-encoder reranker not loaded, skipping rerank")
            return results

        candidates = results[:MAX_RERANK_CANDIDATES]
        remainder = results[MAX_RERANK_CANDIDATES:]

        try:
            pairs = [(query, result.get('question', '')) for result in candidates]
            scores = self.model.predict(pairs)

            reranked = [
                {**result, 'rerank_score': float(score)}
                for result, score in zip(candidates, scores)
            ]
            reranked.sort(key=lambda r: r['rerank_score'], reverse=True)

            return reranked + remainder

        except Exception as e:
            logger.error(f"Error during reranking, keeping fused-rank order: {str(e)}")
            return results
