"""
Knowledge Service
Advanced knowledge base management and search capabilities
"""

from typing import List, Dict, Any, Optional, Tuple
import asyncio
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
import structlog
import hashlib
from collections import defaultdict
import re

from app.core.database import (
    SessionLocal, Question, Answer, Source, UserInteraction,
    DatabaseUtils, CacheUtils
)
from app.core.config import settings
from app.core.monitoring import MetricsCollector
from app.services.ml_service import MLService, TextPreprocessor
from app.services.bm25_service import BM25Index
from app.services.fusion_service import reciprocal_rank_fusion
from app.services.fuzzy_match import CharNgramIndex, BM25_LOW_SCORE_THRESHOLD
from app.services.rerank_service import CrossEncoderReranker, MAX_RERANK_CANDIDATES

logger = structlog.get_logger()


class KnowledgeIndexer:
    """Category/scholar indexing for the knowledge base.

    Keyword indexing previously lived here as a hand-rolled Jaccard-overlap
    inverted index; that's now superseded by BM25Index (proper term
    frequency / inverse document frequency ranking, see bm25_service.py),
    so it's been removed rather than kept as unused dead code.
    """

    def __init__(self):
        self.text_preprocessor = TextPreprocessor()
        self.category_index = defaultdict(set)
        self.scholar_index = defaultdict(set)

    async def build_indexes(self):
        """Build various indexes for fast retrieval"""
        logger.info("Building knowledge base indexes...")

        db = SessionLocal()
        try:
            # Build category index
            await self._build_category_index(db)

            # Build scholar index
            await self._build_scholar_index(db)

            logger.info("Knowledge base indexes built successfully")

        finally:
            db.close()

    async def _build_category_index(self, db: Session):
        """Build category-based index"""
        questions = db.query(Question).filter(Question.category.isnot(None)).all()
        
        for question in questions:
            if question.category:
                self.category_index[question.category.lower()].add(str(question.id))
    
    async def _build_scholar_index(self, db: Session):
        """Build scholar-based index"""
        answers = db.query(Answer).filter(Answer.scholar_name.isnot(None)).all()
        
        for answer in answers:
            if answer.scholar_name:
                self.scholar_index[answer.scholar_name.lower()].add(str(answer.question_id))
    
    def search_by_category(self, category: str) -> set:
        """Search questions by category"""
        return self.category_index.get(category.lower(), set())
    
    def search_by_scholar(self, scholar: str) -> set:
        """Search questions by scholar"""
        return self.scholar_index.get(scholar.lower(), set())


class KnowledgeService:
    """Main knowledge service.

    Hybrid retrieval strategy: fuse FAISS dense-vector results (via
    MLService) with BM25 sparse/lexical results (via BM25Index) using
    Reciprocal Rank Fusion. This replaced the previous AdvancedSearch class
    (Jaccard-keyword-index + broken ILIKE full-text + an always-empty
    semantic-search stub, merged by naive first-seen-wins dedup across two
    incompatible score scales) — see search_knowledge_base below.
    """

    def __init__(self):
        self.indexer = KnowledgeIndexer()
        self.bm25_index = BM25Index()
        self.char_ngram_index = CharNgramIndex()
        self.reranker = CrossEncoderReranker()
        self.ml_service = None
        self.is_initialized = False
    
    async def initialize(self):
        """Initialize the knowledge service"""
        if self.is_initialized:
            return
        
        try:
            logger.info("Initializing Knowledge Service...")

            # Build indexes
            await self.indexer.build_indexes()
            self.bm25_index.build_index()
            self.char_ngram_index.build_index()
            if settings.ENABLE_RERANKING:
                self.reranker.load()

            # Initialize ML service
            self.ml_service = MLService()
            await self.ml_service.initialize_models()

            self.is_initialized = True
            logger.info("Knowledge Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Knowledge Service: {str(e)}")
            # Continue without ML service
            self.is_initialized = True

    async def search_knowledge_base(
        self,
        query: str,
        language: str = 'auto',
        filters: Optional[Dict[str, Any]] = None,
        use_ml: bool = True,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Hybrid search: fuse FAISS dense results and BM25 sparse results
        via Reciprocal Rank Fusion, rather than concatenating a fixed split
        of each and deduplicating first-seen-wins (the old approach)."""
        try:
            filters = filters or {}
            candidate_pool = max(limit * 3, settings.MAX_RESULTS)

            # Dense (FAISS) candidates, keyed by question_id, sorted best-first.
            dense_results_by_id: Dict[str, Dict[str, Any]] = {}
            dense_ranked_ids: List[str] = []
            if use_ml and self.ml_service and settings.ENABLE_ML_MATCHING:
                ml_results = await self.ml_service.process_question(
                    query, language, top_k=candidate_pool
                )
                for result in ml_results.get('results', []):
                    question_id = result['question_id']
                    dense_ranked_ids.append(question_id)
                    dense_results_by_id[question_id] = result

            # Sparse (BM25) candidates, ranked best-first.
            sparse_results = self.bm25_index.search(query, language, top_k=candidate_pool)
            sparse_ranked_ids = [qid for qid, _ in sparse_results]

            # BM25 found little/nothing lexically (e.g. the query is a
            # corrupted/OCR-noisy variant of the indexed text) — fall back to
            # character n-gram similarity, which tolerates dropped/substituted
            # characters that break token-level BM25 matching entirely.
            top_bm25_score = sparse_results[0][1] if sparse_results else 0.0
            fuzzy_ranked_ids: List[str] = []
            if settings.ENABLE_FUZZY_MATCHING and top_bm25_score < BM25_LOW_SCORE_THRESHOLD:
                fuzzy_ranked_ids = self.char_ngram_index.ranked_ids(query, language, top_k=candidate_pool)

            # Fuse by rank position (sidesteps normalizing dense cosine-similarity
            # scores against BM25's unbounded term-frequency scores).
            fused = reciprocal_rank_fusion([dense_ranked_ids, sparse_ranked_ids, fuzzy_ranked_ids])

            # Fetch full result data for any fused hit found only via BM25/fuzzy match.
            missing_ids = [qid for qid, _ in fused if qid not in dense_results_by_id]
            sparse_details_by_id = self._fetch_result_details(missing_ids) if missing_ids else {}

            dense_id_set = set(dense_ranked_ids)
            sparse_id_set = set(sparse_ranked_ids) | set(fuzzy_ranked_ids)

            # Collect a pool larger than `limit` (when reranking is enabled)
            # so the cross-encoder has a meaningful top-K to reorder before
            # truncation, rather than reranking within an already-truncated set.
            # Must stay >= limit, or a caller requesting more than
            # MAX_RERANK_CANDIDATES would silently get back fewer than they asked for
            # (CrossEncoderReranker.rerank already caps the actual rerank pass at
            # MAX_RERANK_CANDIDATES internally and passes the rest through unranked).
            rerank_pool_size = max(limit, MAX_RERANK_CANDIDATES) if settings.ENABLE_RERANKING else limit

            pooled_results = []
            for question_id, fused_score in fused:
                result = dense_results_by_id.get(question_id) or sparse_details_by_id.get(question_id)
                if not result:
                    continue
                if not self._passes_filters(result, filters):
                    continue

                result = dict(result)
                result['fused_score'] = fused_score
                if question_id in dense_id_set and question_id in sparse_id_set:
                    result['search_method'] = 'hybrid'
                elif question_id in dense_id_set:
                    result['search_method'] = 'dense'
                else:
                    result['search_method'] = 'sparse'
                pooled_results.append(result)

                if len(pooled_results) >= rerank_pool_size:
                    break

            if settings.ENABLE_RERANKING:
                pooled_results = self.reranker.rerank(query, pooled_results)

            results = pooled_results[:limit]

            return {
                'query': query,
                'language': language,
                'total_results': len(results),
                'results': results,
                'search_methods_used': self._get_search_methods_used(results)
            }

        except Exception as e:
            logger.error(f"Error searching knowledge base: {str(e)}")
            return {
                'query': query,
                'language': language,
                'total_results': 0,
                'results': [],
                'error': str(e)
            }

    def _fetch_result_details(self, question_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch-fetch question/answer data for BM25-only hits that weren't
        already returned (with full data) by the dense/FAISS pass."""
        db = SessionLocal()
        try:
            questions_by_id = {
                str(q.id): q
                for q in db.query(Question).filter(Question.id.in_(question_ids)).all()
            }

            best_answer_by_question_id: Dict[str, Answer] = {}
            for answer in db.query(Answer).filter(Answer.question_id.in_(question_ids)).all():
                question_id = str(answer.question_id)
                current_best = best_answer_by_question_id.get(question_id)
                if current_best is None or answer.confidence_score > current_best.confidence_score:
                    best_answer_by_question_id[question_id] = answer

            details = {}
            for question_id, question in questions_by_id.items():
                best_answer = best_answer_by_question_id.get(question_id)
                details[question_id] = {
                    'question_id': question_id,
                    'question': question.question_text,
                    'answer': best_answer.answer_text if best_answer else "No answer available",
                    'similarity_score': 0.0,
                    'source_name': best_answer.source_name if best_answer else "Unknown",
                    'source_url': best_answer.source_url if best_answer else "",
                    'scholar_name': best_answer.scholar_name if best_answer else "",
                    'category': question.category,
                    'language': question.language,
                    'confidence_score': best_answer.confidence_score if best_answer else 0.0
                }
            return details
        finally:
            db.close()

    def _passes_filters(self, result: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if a fused result dict passes the given filters."""
        if filters.get('language') and result.get('language') != filters['language']:
            return False

        if filters.get('category') and result.get('category') != filters['category']:
            return False

        return True
    
    async def get_categories(self) -> List[Dict[str, Any]]:
        """Get all available categories with counts"""
        try:
            db = SessionLocal()
            
            # Get category counts
            result = db.execute(text("""
                SELECT category, COUNT(*) as count
                FROM questions
                WHERE category IS NOT NULL
                GROUP BY category
                ORDER BY count DESC
            """))
            
            categories = []
            for row in result:
                categories.append({
                    'name': row.category,
                    'count': row.count,
                    'display_name': row.category.replace('-', ' ').title()
                })
            
            db.close()
            return categories
            
        except Exception as e:
            logger.error(f"Error getting categories: {str(e)}")
            return []
    
    async def get_scholars(self) -> List[Dict[str, Any]]:
        """Get all available scholars with answer counts"""
        try:
            db = SessionLocal()
            
            result = db.execute(text("""
                SELECT scholar_name, COUNT(*) as answer_count
                FROM answers
                WHERE scholar_name IS NOT NULL
                GROUP BY scholar_name
                ORDER BY answer_count DESC
            """))
            
            scholars = []
            for row in result:
                scholars.append({
                    'name': row.scholar_name,
                    'answer_count': row.answer_count
                })
            
            db.close()
            return scholars
            
        except Exception as e:
            logger.error(f"Error getting scholars: {str(e)}")
            return []
    
    async def get_question_by_id(self, question_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific question and its answers"""
        try:
            db = SessionLocal()
            
            question = db.query(Question).filter(Question.id == question_id).first()
            if not question:
                db.close()
                return None
            
            # Get all answers for this question
            answers = db.query(Answer).filter(
                Answer.question_id == question.id
            ).order_by(Answer.confidence_score.desc()).all()
            
            result = {
                'question_id': str(question.id),
                'question': question.question_text,
                'category': question.category,
                'language': question.language,
                'tags': question.tags or [],
                'created_at': question.created_at.isoformat() if question.created_at else None,
                'answers': []
            }
            
            for answer in answers:
                result['answers'].append({
                    'answer_id': str(answer.id),
                    'answer_text': answer.answer_text,
                    'source_name': answer.source_name,
                    'source_url': answer.source_url,
                    'scholar_name': answer.scholar_name,
                    'confidence_score': answer.confidence_score,
                    'is_verified': answer.is_verified,
                    'references': answer.references or {},
                    'created_at': answer.created_at.isoformat() if answer.created_at else None
                })
            
            db.close()
            return result
            
        except Exception as e:
            logger.error(f"Error getting question by ID: {str(e)}")
            return None
    
    async def record_user_interaction(
        self,
        session_id: str,
        query: str,
        results: List[Dict[str, Any]],
        selected_answer_id: Optional[str] = None,
        feedback: Optional[Dict[str, Any]] = None
    ):
        """Record user interaction for analytics"""
        try:
            db = SessionLocal()
            
            interaction = UserInteraction(
                session_id=session_id,
                user_query=query,
                matched_answers=[r['question_id'] for r in results],
                satisfaction_rating=feedback.get('rating') if feedback else None,
                feedback=feedback.get('comment') if feedback else None
            )
            
            db.add(interaction)
            db.commit()
            db.close()
            
        except Exception as e:
            logger.error(f"Error recording user interaction: {str(e)}")
    
    async def get_analytics_summary(self, days: int = 30) -> Dict[str, Any]:
        """Get analytics summary for the knowledge base"""
        try:
            db = SessionLocal()
            
            since_date = datetime.utcnow() - timedelta(days=days)
            
            # Query counts
            total_questions = db.query(Question).count()
            total_answers = db.query(Answer).count()
            recent_interactions = db.query(UserInteraction).filter(
                UserInteraction.created_at >= since_date
            ).count()
            
            # Top categories
            top_categories = db.execute(text("""
                SELECT category, COUNT(*) as count
                FROM questions
                WHERE category IS NOT NULL
                GROUP BY category
                ORDER BY count DESC
                LIMIT 10
            """)).fetchall()
            
            # Language distribution
            language_dist = db.execute(text("""
                SELECT language, COUNT(*) as count
                FROM questions
                GROUP BY language
                ORDER BY count DESC
            """)).fetchall()
            
            db.close()
            
            return {
                'summary': {
                    'total_questions': total_questions,
                    'total_answers': total_answers,
                    'recent_interactions': recent_interactions,
                    'period_days': days
                },
                'top_categories': [
                    {'category': row.category, 'count': row.count}
                    for row in top_categories
                ],
                'language_distribution': [
                    {'language': row.language, 'count': row.count}
                    for row in language_dist
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting analytics summary: {str(e)}")
            return {}
    
    def _get_search_methods_used(self, results: List[Dict[str, Any]]) -> List[str]:
        """Get list of search methods used in results"""
        methods = set()
        for result in results:
            method = result.get('search_method', 'unknown')
            methods.update(method.split(','))
        
        return list(methods)
