"""
Fusion Service Tests
Verifies Reciprocal Rank Fusion behaves as specified, independent of any
retrieval method's DB/ML dependencies.
"""

import pytest

from app.services.fusion_service import reciprocal_rank_fusion


class TestReciprocalRankFusion:
    """Test RRF ranking behavior"""

    def test_empty_lists_return_empty(self):
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[], []]) == []

    def test_single_list_preserves_order(self):
        result = reciprocal_rank_fusion([["a", "b", "c"]])
        assert [doc_id for doc_id, _ in result] == ["a", "b", "c"]

    def test_doc_in_both_lists_outranks_doc_in_one(self):
        """A document appearing in multiple ranked lists should score higher
        than one appearing in only a single list, even if that single list
        ranks it first."""
        list1 = ["b", "a", "c"]
        list2 = ["a", "d"]

        result = reciprocal_rank_fusion([list1, list2])
        ranked_ids = [doc_id for doc_id, _ in result]

        assert ranked_ids[0] == "a"

    def test_score_matches_rrf_formula(self):
        """score(d) = sum(1 / (k + rank + 1)) across lists containing d,
        using 0-indexed rank."""
        k = 60
        result = dict(reciprocal_rank_fusion([["a", "b"]], k=k))

        assert result["a"] == pytest.approx(1 / (k + 1))
        assert result["b"] == pytest.approx(1 / (k + 2))

    def test_higher_rank_scores_higher_within_a_list(self):
        result = dict(reciprocal_rank_fusion([["a", "b", "c"]]))
        assert result["a"] > result["b"] > result["c"]

    def test_results_sorted_descending_by_score(self):
        result = reciprocal_rank_fusion([["c", "a"], ["a", "b"]])
        scores = [score for _, score in result]
        assert scores == sorted(scores, reverse=True)

    def test_document_absent_from_all_lists_not_present(self):
        result = dict(reciprocal_rank_fusion([["a", "b"]]))
        assert "z" not in result

    def test_invalid_k_raises(self):
        with pytest.raises(ValueError):
            reciprocal_rank_fusion([["a"]], k=0)
        with pytest.raises(ValueError):
            reciprocal_rank_fusion([["a"]], k=-1)

    def test_three_lists_fuse_correctly(self):
        """A doc appearing in all three lists should outrank one in two,
        which should outrank one in only one."""
        list1 = ["a", "b", "c"]
        list2 = ["a", "b", "d"]
        list3 = ["a", "c", "e"]

        result = [doc_id for doc_id, _ in reciprocal_rank_fusion([list1, list2, list3])]

        assert result[0] == "a"  # in all three
        assert result.index("b") < result.index("e")  # b in two lists, e in one
