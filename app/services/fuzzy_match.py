"""
Character-Level Fuzzy Matching
Tolerance for corrupted/noisy Arabic text (e.g. OCR-style errors: dropped or
misapplied diacritics, substituted look-alike letters, merged/split
characters) that break both exact word matching and BM25's token-level
matching.

Deliberately scoped small: this is NOT a general fuzzy-search subsystem
(that would duplicate what BM25 + RRF already handle for normal lexical
variation). It's a targeted fallback for when lexical retrieval finds
little or nothing, using character n-grams so a query that differs from the
indexed text by one or two characters still shares most of its n-grams with
the correct match.

Reuses TfidfVectorizer/cosine_similarity (already a project dependency via
scikit-learn) rather than adding a new library.
"""

from typing import List, Tuple

import structlog
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.database import SessionLocal, Question
from app.services.ml_service import TextPreprocessor

logger = structlog.get_logger()

# Below this BM25 top score, lexical matching is considered to have found
# little/nothing, and the char-ngram fallback is worth trying.
BM25_LOW_SCORE_THRESHOLD = 1.0


class CharNgramIndex:
    """Character n-gram similarity index for OCR/noise-tolerant matching."""

    def __init__(self, ngram_range: Tuple[int, int] = (2, 4)):
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=ngram_range)
        self.matrix = None
        self.question_ids: List[str] = []
        self.text_preprocessor = TextPreprocessor()

    def build_index(self):
        """Build the char n-gram TF-IDF matrix over all questions.

        Not persisted to disk (unlike FAISS/BM25) — this is a lightweight
        fallback path, rebuilt in-memory on each service startup, and the
        dataset here is small enough (a portfolio-scale corpus) that this is
        cheap.
        """
        db = SessionLocal()
        try:
            questions = db.query(Question).all()
            if not questions:
                logger.warning("No questions found in database for char n-gram index")
                return

            corpus = []
            question_ids = []
            for question in questions:
                processed = self.text_preprocessor.preprocess_text(
                    question.question_text, question.language
                )
                corpus.append(processed)
                question_ids.append(str(question.id))

            self.fit(corpus, question_ids)
            logger.info(f"Built char n-gram index with {len(questions)} questions")
        finally:
            db.close()

    def fit(self, corpus: List[str], ids: List[str]):
        """Build the char n-gram TF-IDF matrix from already-preprocessed
        documents directly, for callers whose documents don't come from the
        Question table (e.g. VoiceSearchService's Quran ayah corpus)."""
        self.matrix = self.vectorizer.fit_transform(corpus)
        self.question_ids = ids

    def search(self, query: str, language: str = "auto", top_k: int = 10) -> List[Tuple[str, float]]:
        """Return (question_id, similarity) pairs sorted best-first."""
        if self.matrix is None or not self.question_ids:
            return []

        processed_query = self.text_preprocessor.preprocess_text(query, language)
        if not processed_query.strip():
            return []

        query_vector = self.vectorizer.transform([processed_query])
        similarities = cosine_similarity(query_vector, self.matrix)[0]

        scored = [
            (self.question_ids[i], float(score))
            for i, score in enumerate(similarities)
            if score > 0
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        return scored[:top_k]

    def ranked_ids(self, query: str, language: str = "auto", top_k: int = 10) -> List[str]:
        """Convenience wrapper returning just the ranked question_id list."""
        return [question_id for question_id, _ in self.search(query, language, top_k)]
