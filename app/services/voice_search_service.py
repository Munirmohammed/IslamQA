"""
Voice Search Service ("Tasmeea")
Given a recited (or, for now, typed) Quran fragment, find the matching
ayah(s)/surah -- the same job Tarteel's "Tasmeea" feature does. Speech-to-text
itself is a later phase; this service takes the transcript text directly.

Mirrors KnowledgeService.search_knowledge_base's hybrid retrieval strategy
(BM25 sparse + FAISS dense, fused via Reciprocal Rank Fusion, cross-encoder
reranked, char n-gram fuzzy fallback for noisy transcripts) but operates over
the Quran ayah corpus (quran_corpus_service.py) instead of the Question/Answer
DB table, since ayahs aren't DB-backed. Reuses BM25Index/CharNgramIndex/
reciprocal_rank_fusion/CrossEncoderReranker as-is (their `fit`/`rerank`
entry points were generalized to accept an arbitrary corpus); the FAISS dense
index is built directly here, since VectorEmbeddings' equivalent is tightly
coupled to Question/Answer DB hydration and Redis embedding caching that
don't apply to this static corpus.
"""

import os
from typing import Any, Dict, List, Tuple

import faiss
import numpy as np
import structlog
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.services.bm25_service import BM25Index
from app.services.fuzzy_match import CharNgramIndex, BM25_LOW_SCORE_THRESHOLD
from app.services.fusion_service import reciprocal_rank_fusion
from app.services.ml_service import TextPreprocessor
from app.services.quran_corpus_service import QuranCorpusService
from app.services.rerank_service import CrossEncoderReranker, MAX_RERANK_CANDIDATES

logger = structlog.get_logger()

DATA_DIR = "data/quran"
BM25_INDEX_PATH = os.path.join(DATA_DIR, "quran_bm25_index.pkl")
BM25_IDS_PATH = os.path.join(DATA_DIR, "quran_bm25_keys.pkl")
FAISS_INDEX_PATH = os.path.join(DATA_DIR, "quran_faiss_index.bin")

# Diacritic-free edition: closest to what an ASR transcript of a recitation
# (or a user's best-effort typed fragment) actually looks like.
SEARCH_TEXT_FIELD = "text_simple"


class VoiceSearchService:
    """Hybrid (BM25 + FAISS, RRF-fused, reranked) search over Quran ayahs."""

    def __init__(self):
        self.corpus_service = QuranCorpusService()
        self.text_preprocessor = TextPreprocessor()
        self.bm25_index = BM25Index(index_path=BM25_INDEX_PATH, ids_path=BM25_IDS_PATH)
        self.char_ngram_index = CharNgramIndex()
        self.reranker = CrossEncoderReranker()
        self.dense_model: SentenceTransformer = None
        self.faiss_index = None
        self.ayah_keys: List[str] = []
        self.ayahs_by_key: Dict[str, Dict[str, Any]] = {}
        self.is_initialized = False

    async def initialize(self, force_rebuild: bool = False):
        if self.is_initialized:
            return

        try:
            logger.info("Initializing Voice Search Service...")
            ayahs = self.corpus_service.load_or_fetch()
            self.ayahs_by_key = {ayah["key"]: ayah for ayah in ayahs}

            self._build_bm25_index(ayahs, force_rebuild)
            self._build_char_ngram_index(ayahs)
            self._build_faiss_index(ayahs, force_rebuild)

            if settings.ENABLE_RERANKING:
                self.reranker.load()

            self.is_initialized = True
            logger.info("Voice Search Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Voice Search Service: {str(e)}")
            # Degrade gracefully rather than failing app startup, matching
            # KnowledgeService.initialize's convention.
            self.is_initialized = True

    def _build_bm25_index(self, ayahs: List[Dict[str, Any]], force_rebuild: bool):
        if not force_rebuild and self.bm25_index.load():
            self.ayah_keys = self.bm25_index.question_ids
            return

        tokenized_corpus = [
            self.text_preprocessor.preprocess_text(ayah[SEARCH_TEXT_FIELD], "ar").split()
            for ayah in ayahs
        ]
        ayah_keys = [ayah["key"] for ayah in ayahs]
        self.bm25_index.fit(tokenized_corpus, ayah_keys)
        self.ayah_keys = ayah_keys
        logger.info(f"Built Quran BM25 index with {len(ayahs)} ayahs")

    def _build_char_ngram_index(self, ayahs: List[Dict[str, Any]]):
        corpus = [
            self.text_preprocessor.preprocess_text(ayah[SEARCH_TEXT_FIELD], "ar")
            for ayah in ayahs
        ]
        ayah_keys = [ayah["key"] for ayah in ayahs]
        self.char_ngram_index.fit(corpus, ayah_keys)
        logger.info(f"Built Quran char n-gram index with {len(ayahs)} ayahs")

    def _build_faiss_index(self, ayahs: List[Dict[str, Any]], force_rebuild: bool):
        self.dense_model = SentenceTransformer(settings.SENTENCE_TRANSFORMER_MODEL, device="cpu")

        if not force_rebuild and os.path.exists(FAISS_INDEX_PATH):
            try:
                self.faiss_index = faiss.read_index(FAISS_INDEX_PATH)
                logger.info(
                    f"Loaded existing Quran FAISS index with {self.faiss_index.ntotal} ayahs"
                )
                return
            except Exception:
                logger.warning("Failed to load existing Quran FAISS index, rebuilding...")

        texts = [ayah[SEARCH_TEXT_FIELD] for ayah in ayahs]
        embeddings = self.dense_model.encode(texts, show_progress_bar=False, batch_size=64)
        embeddings_matrix = np.array(embeddings).astype("float32")
        faiss.normalize_L2(embeddings_matrix)

        index = faiss.IndexFlatIP(embeddings_matrix.shape[1])
        index.add(embeddings_matrix)
        self.faiss_index = index

        os.makedirs(DATA_DIR, exist_ok=True)
        faiss.write_index(index, FAISS_INDEX_PATH)
        logger.info(f"Built Quran FAISS index with {len(ayahs)} ayahs")

    def _dense_search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        if not self.faiss_index or not self.ayah_keys:
            return []

        query_vector = np.array(self.dense_model.encode([query])).astype("float32")
        faiss.normalize_L2(query_vector)
        similarities, indices = self.faiss_index.search(query_vector, top_k)

        results = []
        for similarity, idx in zip(similarities[0], indices[0]):
            # FAISS pads with idx == -1 when fewer real matches exist than requested.
            if idx < 0 or idx >= len(self.ayah_keys):
                continue
            results.append((self.ayah_keys[idx], float(similarity)))
        return results

    async def search(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """Find the ayah(s) matching a recited/typed Quran fragment."""
        if not self.is_initialized:
            await self.initialize()

        candidate_pool = max(top_k * 3, 30)

        dense_ranked_keys = [key for key, _ in self._dense_search(query, candidate_pool)]
        sparse_results = self.bm25_index.search(query, "ar", top_k=candidate_pool)
        sparse_ranked_keys = [key for key, _ in sparse_results]

        # BM25 found little/nothing lexically (e.g. a noisy ASR transcript) --
        # fall back to character n-gram similarity, same trigger condition as
        # KnowledgeService.search_knowledge_base.
        top_bm25_score = sparse_results[0][1] if sparse_results else 0.0
        fuzzy_ranked_keys: List[str] = []
        if settings.ENABLE_FUZZY_MATCHING and top_bm25_score < BM25_LOW_SCORE_THRESHOLD:
            fuzzy_ranked_keys = self.char_ngram_index.ranked_ids(query, "ar", top_k=candidate_pool)

        fused = reciprocal_rank_fusion([dense_ranked_keys, sparse_ranked_keys, fuzzy_ranked_keys])

        rerank_pool_size = max(top_k, MAX_RERANK_CANDIDATES) if settings.ENABLE_RERANKING else top_k

        pooled_results = []
        for key, fused_score in fused:
            ayah = self.ayahs_by_key.get(key)
            if not ayah:
                continue
            result = dict(ayah)
            result["fused_score"] = fused_score
            pooled_results.append(result)
            if len(pooled_results) >= rerank_pool_size:
                break

        if settings.ENABLE_RERANKING:
            pooled_results = self.reranker.rerank(query, pooled_results, text_field=SEARCH_TEXT_FIELD)

        results = pooled_results[:top_k]

        return {
            "query": query,
            "total_results": len(results),
            "results": results,
        }


voice_search_service = VoiceSearchService()
