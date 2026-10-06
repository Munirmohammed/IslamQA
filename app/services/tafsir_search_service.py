"""
Tafsir Search Service
Free-text search over the tafsir corpus (tafsir_service.py) -- "ask a
question, get the relevant scholarly commentary." Structurally a direct
copy of voice_search_service.py's pattern (BM25 + FAISS + RRF fusion +
cross-encoder rerank, reusing the same already-generalized Phase 1 pieces),
indexed over each tafsir block's text_plain instead of ayah text.

Deliberately a separate service/index from voice_search_service rather than
sharing one: a block here represents a possibly-multi-ayah commentary
passage, not a single ayah, so it has its own document identity (see
_unique_blocks below) distinct from an ayah key.
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
from app.services.rerank_service import CrossEncoderReranker, MAX_RERANK_CANDIDATES
from app.services.tafsir_service import TafsirService

logger = structlog.get_logger()

DATA_DIR = "data/quran"
BM25_INDEX_PATH = os.path.join(DATA_DIR, "tafsir_bm25_index.pkl")
BM25_IDS_PATH = os.path.join(DATA_DIR, "tafsir_bm25_keys.pkl")
FAISS_INDEX_PATH = os.path.join(DATA_DIR, "tafsir_faiss_index.bin")

SEARCH_TEXT_FIELD = "text_plain"


def _unique_blocks(by_key: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Many ayah keys can point to the same (possibly multi-ayah) tafsir
    block; index each distinct block once, not once per ayah it covers."""
    unique: Dict[str, Dict[str, Any]] = {}
    for block in by_key.values():
        block_id = f"{block['surah_number']}:{block['ayah_from']}-{block['ayah_to']}"
        unique[block_id] = block
    return unique


class TafsirSearchService:
    """Hybrid (BM25 + FAISS, RRF-fused, reranked) search over tafsir blocks."""

    def __init__(self):
        self.tafsir_service = TafsirService()
        self.text_preprocessor = TextPreprocessor()
        self.bm25_index = BM25Index(index_path=BM25_INDEX_PATH, ids_path=BM25_IDS_PATH)
        self.char_ngram_index = CharNgramIndex()
        self.reranker = CrossEncoderReranker()
        self.dense_model: SentenceTransformer = None
        self.faiss_index = None
        self.block_keys: List[str] = []
        self.blocks_by_key: Dict[str, Dict[str, Any]] = {}
        self.is_initialized = False

    async def initialize(self, force_rebuild: bool = False):
        if self.is_initialized:
            return

        try:
            logger.info("Initializing Tafsir Search Service...")
            self.tafsir_service.load_or_fetch()
            self.blocks_by_key = _unique_blocks(self.tafsir_service.get_all_blocks_by_key())
            blocks = list(self.blocks_by_key.values())
            self.block_keys = list(self.blocks_by_key.keys())

            self._build_bm25_index(blocks, force_rebuild)
            self._build_char_ngram_index(blocks)
            self._build_faiss_index(blocks, force_rebuild)

            if settings.ENABLE_RERANKING:
                self.reranker.load()

            self.is_initialized = True
            logger.info("Tafsir Search Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Tafsir Search Service: {str(e)}")
            self.is_initialized = True

    def _block_id(self, block: Dict[str, Any]) -> str:
        return f"{block['surah_number']}:{block['ayah_from']}-{block['ayah_to']}"

    def _build_bm25_index(self, blocks: List[Dict[str, Any]], force_rebuild: bool):
        if not force_rebuild and self.bm25_index.load():
            return

        tokenized_corpus = [
            self.text_preprocessor.preprocess_text(b[SEARCH_TEXT_FIELD], "en").split()
            for b in blocks
        ]
        block_ids = [self._block_id(b) for b in blocks]
        self.bm25_index.fit(tokenized_corpus, block_ids)
        logger.info(f"Built tafsir BM25 index with {len(blocks)} blocks")

    def _build_char_ngram_index(self, blocks: List[Dict[str, Any]]):
        corpus = [
            self.text_preprocessor.preprocess_text(b[SEARCH_TEXT_FIELD], "en")
            for b in blocks
        ]
        block_ids = [self._block_id(b) for b in blocks]
        self.char_ngram_index.fit(corpus, block_ids)
        logger.info(f"Built tafsir char n-gram index with {len(blocks)} blocks")

    def _build_faiss_index(self, blocks: List[Dict[str, Any]], force_rebuild: bool):
        self.dense_model = SentenceTransformer(settings.SENTENCE_TRANSFORMER_MODEL, device="cpu")

        if not force_rebuild and os.path.exists(FAISS_INDEX_PATH):
            try:
                self.faiss_index = faiss.read_index(FAISS_INDEX_PATH)
                logger.info(f"Loaded existing tafsir FAISS index with {self.faiss_index.ntotal} blocks")
                return
            except Exception:
                logger.warning("Failed to load existing tafsir FAISS index, rebuilding...")

        texts = [b[SEARCH_TEXT_FIELD] for b in blocks]
        embeddings = self.dense_model.encode(texts, show_progress_bar=False, batch_size=32)
        embeddings_matrix = np.array(embeddings).astype("float32")
        faiss.normalize_L2(embeddings_matrix)

        index = faiss.IndexFlatIP(embeddings_matrix.shape[1])
        index.add(embeddings_matrix)
        self.faiss_index = index

        os.makedirs(DATA_DIR, exist_ok=True)
        faiss.write_index(index, FAISS_INDEX_PATH)
        logger.info(f"Built tafsir FAISS index with {len(blocks)} blocks")

    def _dense_search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        if not self.faiss_index or not self.block_keys:
            return []

        query_vector = np.array(self.dense_model.encode([query])).astype("float32")
        faiss.normalize_L2(query_vector)
        similarities, indices = self.faiss_index.search(query_vector, top_k)

        results = []
        for similarity, idx in zip(similarities[0], indices[0]):
            if idx < 0 or idx >= len(self.block_keys):
                continue
            results.append((self.block_keys[idx], float(similarity)))
        return results

    async def search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Find the tafsir block(s) most relevant to a free-text question."""
        if not self.is_initialized:
            await self.initialize()

        candidate_pool = max(top_k * 3, 30)

        dense_ranked_ids = [key for key, _ in self._dense_search(query, candidate_pool)]
        sparse_results = self.bm25_index.search(query, "en", top_k=candidate_pool)
        sparse_ranked_ids = [key for key, _ in sparse_results]

        top_bm25_score = sparse_results[0][1] if sparse_results else 0.0
        fuzzy_ranked_ids: List[str] = []
        if settings.ENABLE_FUZZY_MATCHING and top_bm25_score < BM25_LOW_SCORE_THRESHOLD:
            fuzzy_ranked_ids = self.char_ngram_index.ranked_ids(query, "en", top_k=candidate_pool)

        fused = reciprocal_rank_fusion([dense_ranked_ids, sparse_ranked_ids, fuzzy_ranked_ids])

        rerank_pool_size = max(top_k, MAX_RERANK_CANDIDATES) if settings.ENABLE_RERANKING else top_k

        pooled_results = []
        for block_id, fused_score in fused:
            block = self.blocks_by_key.get(block_id)
            if not block:
                continue
            result = dict(block)
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


tafsir_search_service = TafsirSearchService()
