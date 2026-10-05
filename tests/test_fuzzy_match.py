"""
OCR/Noise-Tolerance Proof
Demonstrates the actual point of the char n-gram fallback (fuzzy_match.py):
a short keyword/name-style query with a realistic OCR letter-confusion error
(dot-difference substitutions like ج/ح, ز/ر, ع/غ -- NOT the alef/hamza/teh
variants that preprocess_arabic's pyarabic normalization already unifies)
should still find its document via character n-gram similarity, even where
BM25's exact-token matching has zero signal to work with.

Why single-keyword queries specifically: this codebase's local dataset is
tiny (a handful of questions), and empirically, corrupting one word inside a
multi-word question query does NOT defeat BM25 here -- the query's other,
uncorrupted words still uniquely identify the right document among so few
candidates. That's a real property of this corpus, not a flaw in the fix.
The genuinely OCR-vulnerable case -- and the one the essay answers this
project's demo is meant to substantiate -- is exactly what a real user
search for a specific name or term looks like: a short, one-or-two-word
query with no redundant context to fall back on. See
tests/fixtures/ocr_keyword_queries.json for the corruption pairs used here
(each hand-verified to genuinely zero out BM25's score for the correct
document before being added).
"""

import json
import os

import pytest

from app.services.bm25_service import BM25Index
from app.services.fuzzy_match import CharNgramIndex

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "ocr_keyword_queries.json")


def load_ocr_keyword_queries():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.slow
@pytest.mark.integration
def test_char_ngram_index_finds_document_for_corrupted_keyword():
    """Every corrupted single-keyword query should still retrieve its
    expected document via character n-gram similarity."""
    queries = load_ocr_keyword_queries()
    assert queries, "expected at least one OCR keyword query fixture"

    char_ngram_index = CharNgramIndex()
    char_ngram_index.build_index()

    misses = []
    for item in queries:
        ranked_ids = char_ngram_index.ranked_ids(item["corrupted_word"], "ar", top_k=5)
        if item["expected_question_id"] not in ranked_ids[:1]:
            misses.append((item["corrupted_word"], ranked_ids))

    assert not misses, f"char n-gram fallback failed to rank these correctly at top-1: {misses}"


@pytest.mark.slow
@pytest.mark.integration
def test_bm25_alone_has_zero_signal_on_corrupted_keyword():
    """Contrast case: BM25's token-level matching gives zero score to the
    correct document for every one of these corrupted single-keyword
    queries -- this is precisely the gap the char n-gram fallback exists
    to close, and why search_knowledge_base triggers it when BM25's top
    score is low (see BM25_LOW_SCORE_THRESHOLD in fuzzy_match.py)."""
    queries = load_ocr_keyword_queries()

    bm25_index = BM25Index()
    bm25_index.build_index()

    non_zero = []
    for item in queries:
        scored = dict(bm25_index.search(item["corrupted_word"], "ar", top_k=10))
        correct_doc_score = scored.get(item["expected_question_id"], 0.0)
        if correct_doc_score > 0.0:
            non_zero.append((item["corrupted_word"], correct_doc_score))

    assert not non_zero, (
        f"expected BM25 to have zero signal for the correct document on these corrupted "
        f"keywords, but got non-zero scores: {non_zero} -- if this fails, the fixture pairs "
        f"may no longer be realistic OCR-style noise for the current corpus"
    )
