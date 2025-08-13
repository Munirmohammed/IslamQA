"""
Knowledge Service
Advanced knowledge base management and search capabilities
"""

from typing import List, Dict, Any, Optional, Tuple
import asyncio
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text, or_, and_
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

logger = structlog.get_logger()


class KnowledgeIndexer:
    """Advanced indexing for the knowledge base"""
    
    def __init__(self):
        self.text_preprocessor = TextPreprocessor()
        self.keyword_index = defaultdict(set)
        self.category_index = defaultdict(set)
        self.scholar_index = defaultdict(set)
    
    async def build_indexes(self):
        """Build various indexes for fast retrieval"""
        logger.info("Building knowledge base indexes...")
        
        db = SessionLocal()
        try:
            # Build keyword index
            await self._build_keyword_index(db)
            
            # Build category index
            await self._build_category_index(db)
            
            # Build scholar index
            await self._build_scholar_index(db)
            
            logger.info("Knowledge base indexes built successfully")
            
        finally:
            db.close()
    
    async def _build_keyword_index(self, db: Session):
        """Build keyword-based index"""
        questions = db.query(Question).all()
        
        for question in questions:
            # Extract keywords from question
            keywords = self._extract_keywords(question.question_text, question.language)
            
            for keyword in keywords:
                self.keyword_index[keyword].add(str(question.id))
    
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
    
    def _extract_keywords(self, text: str, language: str) -> List[str]:
        """Extract important keywords from text"""
        processed_text = self.text_preprocessor.preprocess_text(text, language)
        words = processed_text.split()
        
        # Filter by length and importance
        keywords = [word for word in words if len(word) > 3]
        
        return keywords[:20]  # Limit to top 20 keywords
    
    def search_by_keywords(self, keywords: List[str]) -> set:
        """Search questions by keywords"""
        if not keywords:
            return set()
        
        # Find intersection of keyword results
        result_sets = [self.keyword_index.get(keyword.lower(), set()) for keyword in keywords]
        
        if not result_sets:
            return set()
        
        # Start with first set
        results = result_sets[0]
        
        # Intersect with other sets
        for result_set in result_sets[1:]:
            results = results.intersection(result_set)
        
        return results
    
    def search_by_category(self, category: str) -> set:
        """Search questions by category"""
        return self.category_index.get(category.lower(), set())
    
    def search_by_scholar(self, scholar: str) -> set:
        """Search questions by scholar"""
        return self.scholar_index.get(scholar.lower(), set())


class AdvancedSearch:
    """Advanced search capabilities"""
    
    def __init__(self, indexer: KnowledgeIndexer):
        self.indexer = indexer
        self.text_preprocessor = TextPreprocessor()
    
    async def search(
        self, 
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = 'relevance',
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Advanced search with multiple strategies"""
        try:
            filters = filters or {}
            results = []
            
            # Strategy 1: Keyword-based search
            keyword_results = await self._keyword_search(query, filters)
            results.extend(keyword_results)
            
            # Strategy 2: Semantic search (if ML service available)
            semantic_results = await self._semantic_search(query, filters)
            results.extend(semantic_results)
            
            # Strategy 3: Full-text search
            fulltext_results = await self._fulltext_search(query, filters)
            results.extend(fulltext_results)
            
            # Deduplicate and score
            final_results = self._deduplicate_and_score(results, query)
            
            # Sort results
            sorted_results = self._sort_results(final_results, sort_by)
            
            return sorted_results[:limit]
            
        except Exception as e:
            logger.error(f"Error in advanced search: {str(e)}")
            return []
    
    async def _keyword_search(self, query: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Keyword-based search using indexes"""
        try:
            # Extract keywords from query
            language = self.text_preprocessor.detect_language(query)
            keywords = self.text_preprocessor.preprocess_text(query, language).split()
            
            # Search using keyword index
            question_ids = self.indexer.search_by_keywords(keywords)
            
            if not question_ids:
                return []
            
            # Get question details from database
            db = SessionLocal()
            try:
                questions = db.query(Question).filter(
                    Question.id.in_(question_ids)
                ).all()
                
                results = []
                for question in questions:
                    # Apply filters
                    if not self._passes_filters(question, filters):
                        continue
                    
                    # Get best answer
                    best_answer = db.query(Answer).filter(
                        Answer.question_id == question.id
                    ).order_by(Answer.confidence_score.desc()).first()
                    
                    result = {
                        'question_id': str(question.id),
                        'question': question.question_text,
                        'answer': best_answer.answer_text if best_answer else "",
                        'source_name': best_answer.source_name if best_answer else "",
                        'scholar_name': best_answer.scholar_name if best_answer else "",
                        'category': question.category,
                        'language': question.language,
                        'search_method': 'keyword',
                        'relevance_score': self._calculate_keyword_relevance(query, question.question_text)
                    }
                    results.append(result)
                
                return results
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in keyword search: {str(e)}")
            return []
    
    async def _semantic_search(self, query: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Semantic search using ML service"""
        try:
            # This would use the ML service for semantic similarity
            # For now, return empty list if ML service is not available
            return []
            
        except Exception as e:
            logger.error(f"Error in semantic search: {str(e)}")
            return []
    
    async def _fulltext_search(self, query: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Full-text search using database capabilities"""
        try:
            db = SessionLocal()
            try:
                # Build full-text search query
                search_terms = query.split()
                search_conditions = []
                
                for term in search_terms:
                    search_conditions.append(
                        or_(
                            Question.question_text.ilike(f"%{term}%"),
                            Question.category.ilike(f"%{term}%")
                        )
                    )
                
                if not search_conditions:
                    return []
                
                # Execute search
                questions = db.query(Question).filter(
                    or_(*search_conditions)
                ).limit(50).all()
                
                results = []
                for question in questions:
                    # Apply filters
                    if not self._passes_filters(question, filters):
                        continue
                    
                    # Get best answer
                    best_answer = db.query(Answer).filter(
                        Answer.question_id == question.id
                    ).order_by(Answer.confidence_score.desc()).first()
                    
                    result = {
                        'question_id': str(question.id),
                        'question': question.question_text,
                        'answer': best_answer.answer_text if best_answer else "",
                        'source_name': best_answer.source_name if best_answer else "",
                        'scholar_name': best_answer.scholar_name if best_answer else "",
                        'category': question.category,
                        'language': question.language,
                        'search_method': 'fulltext',
                        'relevance_score': self._calculate_fulltext_relevance(query, question.question_text)
                    }
                    results.append(result)
                
                return results
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in fulltext search: {str(e)}")
            return []
    
    def _passes_filters(self, question: Question, filters: Dict[str, Any]) -> bool:
        """Check if question passes the given filters"""
        if filters.get('language') and question.language != filters['language']:
            return False
        
        if filters.get('category') and question.category != filters['category']:
            return False
        
        if filters.get('source'):
            # Would need to check answer source
            pass
        
        return True
    
    def _calculate_keyword_relevance(self, query: str, question_text: str) -> float:
        """Calculate relevance score for keyword search"""
        query_words = set(query.lower().split())
        question_words = set(question_text.lower().split())
        
        overlap = len(query_words.intersection(question_words))
        total = len(query_words.union(question_words))
        
        return overlap / total if total > 0 else 0.0
    
    def _calculate_fulltext_relevance(self, query: str, question_text: str) -> float:
        """Calculate relevance score for fulltext search"""
        # Simple scoring based on term frequency
        query_terms = query.lower().split()
        question_lower = question_text.lower()
        
        score = 0.0
        for term in query_terms:
            count = question_lower.count(term)
            score += count
        
        # Normalize by question length
        return score / len(question_text.split()) if question_text else 0.0
    
    def _deduplicate_and_score(self, results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Remove duplicates and combine scores"""
        unique_results = {}
        
        for result in results:
            question_id = result['question_id']
            
            if question_id in unique_results:
                # Combine scores from different search methods
                existing = unique_results[question_id]
                existing['relevance_score'] = max(
                    existing['relevance_score'], 
                    result['relevance_score']
                )
                existing['search_method'] = f"{existing['search_method']},{result['search_method']}"
            else:
                unique_results[question_id] = result
        
        return list(unique_results.values())
    
    def _sort_results(self, results: List[Dict[str, Any]], sort_by: str) -> List[Dict[str, Any]]:
        """Sort results by specified criteria"""
        if sort_by == 'relevance':
            return sorted(results, key=lambda x: x['relevance_score'], reverse=True)
        elif sort_by == 'date':
            # Would need creation date in results
            return results
        else:
            return results


class KnowledgeService:
    """Main knowledge service"""
    
    def __init__(self):
        self.indexer = KnowledgeIndexer()
        self.advanced_search = AdvancedSearch(self.indexer)
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
        """Search the knowledge base with multiple strategies"""
        try:
            results = []
            
            # Use ML service if available and requested
            if use_ml and self.ml_service and settings.ENABLE_ML_MATCHING:
                ml_results = await self.ml_service.process_question(query, language)
                if ml_results.get('results'):
                    results.extend(ml_results['results'][:limit//2])
            
            # Use advanced search for additional results
            search_results = await self.advanced_search.search(
                query, 
                filters, 
                limit=limit - len(results)
            )
            results.extend(search_results)
            
            # Deduplicate
            unique_results = self._deduplicate_results(results)
            
            return {
                'query': query,
                'language': language,
                'total_results': len(unique_results),
                'results': unique_results[:limit],
                'search_methods_used': self._get_search_methods_used(unique_results)
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
    
    def _deduplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate results"""
        seen = set()
        unique_results = []
        
        for result in results:
            question_id = result.get('question_id')
            if question_id and question_id not in seen:
                seen.add(question_id)
                unique_results.append(result)
        
        return unique_results
    
    def _get_search_methods_used(self, results: List[Dict[str, Any]]) -> List[str]:
        """Get list of search methods used in results"""
        methods = set()
        for result in results:
            method = result.get('search_method', 'unknown')
            methods.update(method.split(','))
        
        return list(methods)
