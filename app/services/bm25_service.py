"""
BM25 Sparse Retrieval Service
Proper BM25 (Okapi) ranking over the question corpus, replacing the ad hoc
Jaccard-overlap keyword index and unnormalized ILIKE full-text search that
KnowledgeIndexer/AdvancedSearch used previously. Mirrors
VectorEmbeddings.build_faiss_index's load-or-build persistence pattern so the
two indexes (dense FAISS, sparse BM25) behave consistently.
"""

import os
import pickle
from typing import List, Tuple

import structlog
from rank_bm25 import BM25Okapi

from app.core.database import SessionLocal, Question
from app.services.ml_service import TextPreprocessor

logger = structlog.get_logger()

INDEX_PATH = "data/bm25_index.pkl"
IDS_PATH = "data/bm25_question_ids.pkl"


class BM25Index:
    """Sparse (lexical) retrieval index built with BM25Okapi."""

    def __init__(self, index_path: str = INDEX_PATH, ids_path: str = IDS_PATH):
        self.bm25: BM25Okapi = None
        self.question_ids: List[str] = []
        self.text_preprocessor = TextPreprocessor()
        self.index_path = index_path
        self.ids_path = ids_path

    def load(self) -> bool:
        """Try loading a persisted index from disk. Returns True on success,
        so a caller whose documents don't come from the Question table (e.g.
        VoiceSearchService) can reuse the disk cache without going through
        build_index's Question-table fallback."""
        if not (os.path.exists(self.index_path) and os.path.exists(self.ids_path)):
            return False
        try:
            with open(self.index_path, "rb") as f:
                self.bm25 = pickle.load(f)
            with open(self.ids_path, "rb") as f:
                self.question_ids = pickle.load(f)
            logger.info(f"Loaded existing BM25 index with {len(self.question_ids)} questions")
            return True
        except Exception:
            logger.warning("Failed to load existing BM25 index, rebuilding...")
            return False

    def build_index(self, force_rebuild: bool = False):
        """Build (or load a persisted) BM25 index over all questions."""
        if not force_rebuild and self.load():
            return

        logger.info("Building new BM25 index...")

        db = SessionLocal()
        try:
            questions = db.query(Question).all()

            if not questions:
                logger.warning("No questions found in database")
                return

            tokenized_corpus = []
            question_ids = []

            for question in questions:
                processed = self.text_preprocessor.preprocess_text(
                    question.question_text, question.language
                )
                tokenized_corpus.append(processed.split())
                question_ids.append(str(question.id))

            self.fit(tokenized_corpus, question_ids)
            logger.info(f"Built BM25 index with {len(questions)} questions")

        finally:
            db.close()

    def fit(self, tokenized_corpus: List[List[str]], ids: List[str]):
        """Build and persist the BM25 index directly from an already-tokenized
        corpus, for callers whose documents don't come from the Question
        table (e.g. VoiceSearchService's Quran ayah corpus)."""
        self.bm25 = BM25Okapi(tokenized_corpus)
        self.question_ids = ids

        os.makedirs(os.path.dirname(self.index_path) or ".", exist_ok=True)
        with open(self.index_path, "wb") as f:
            pickle.dump(self.bm25, f)
        with open(self.ids_path, "wb") as f:
            pickle.dump(ids, f)

    def search(self, query: str, language: str = "auto", top_k: int = 10) -> List[Tuple[str, float]]:
        """Return (question_id, bm25_score) pairs sorted best-first.

        Only positive-scoring matches are returned, since a zero BM25 score
        means none of the query terms occur in that document at all.
        """
        if not self.bm25 or not self.question_ids:
            return []

        processed_query = self.text_preprocessor.preprocess_text(query, language)
        query_tokens = processed_query.split()

        if not query_tokens:
            return []

        scores = self.bm25.get_scores(query_tokens)

        scored = [
            (self.question_ids[i], float(score))
            for i, score in enumerate(scores)
            if score > 0
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        return scored[:top_k]

    def ranked_ids(self, query: str, language: str = "auto", top_k: int = 10) -> List[str]:
        """Convenience wrapper returning just the ranked question_id list."""
        return [question_id for question_id, _ in self.search(query, language, top_k)]
