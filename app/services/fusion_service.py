"""
Rank Fusion Service
Combines multiple ranked retrieval results (e.g. FAISS dense search, BM25
sparse search) into a single ranking via Reciprocal Rank Fusion (RRF).

RRF fuses by rank position rather than raw score, which avoids having to
normalize/calibrate scores across retrieval methods that live on different,
incompatible scales (e.g. FAISS cosine similarity in [0, 1] vs. BM25's
unbounded term-frequency scores).
"""

from typing import Dict, List, Sequence, Tuple

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[str]],
    k: int = DEFAULT_RRF_K,
) -> List[Tuple[str, float]]:
    """Fuse multiple ranked lists of document IDs via Reciprocal Rank Fusion.

    For each list, a document at 0-indexed rank r contributes 1 / (k + r + 1)
    to its fused score. A document appearing in more lists, or ranked higher
    within a list, accumulates a higher fused score. Documents absent from a
    list simply don't receive a contribution from it.

    Args:
        ranked_lists: one or more ranked sequences of document IDs, each
            already sorted best-first by that retrieval method.
        k: RRF's rank-damping constant. Higher k flattens the influence of
            rank position; 60 is the standard default from the original RRF
            paper (Cormack et al., 2009) and works well without tuning.

    Returns:
        (document_id, fused_score) pairs sorted by fused_score descending.
        Ties are broken by preserving the order in which document IDs were
        first encountered across the input lists (stable sort).
    """
    if k <= 0:
        raise ValueError("k must be positive")

    scores: Dict[str, float] = {}
    first_seen_order: Dict[str, int] = {}
    position = 0

    for ranked_list in ranked_lists:
        for rank, doc_id in enumerate(ranked_list):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            if doc_id not in first_seen_order:
                first_seen_order[doc_id] = position
                position += 1

    return sorted(
        scores.items(),
        key=lambda item: (-item[1], first_seen_order[item[0]]),
    )
