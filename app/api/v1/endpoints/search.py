"""
Search Endpoints
Advanced search functionality for the Islamic Q&A knowledge base
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import uuid

from app.core.database import get_db, User
from app.core.security import get_optional_user, RateLimiter
from app.services.knowledge_service import KnowledgeService
from app.services.ml_service import MLService
from app.core.monitoring import MetricsCollector

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    language: str = Field(default="auto", description="Language preference (auto, en, ar)")
    category: Optional[str] = Field(default=None, description="Category filter")
    scholar: Optional[str] = Field(default=None, description="Scholar filter")
    source: Optional[str] = Field(default=None, description="Source filter")
    use_ml: bool = Field(default=True, description="Use ML-powered search")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum results")


class SearchResult(BaseModel):
    question_id: str
    question: str
    answer: str
    similarity_score: float
    source_name: str
    source_url: Optional[str]
    scholar_name: Optional[str]
    category: Optional[str]
    language: str
    confidence_score: float
    is_verified: bool


class SearchResponse(BaseModel):
    query: str
    language: str
    total_results: int
    results: List[SearchResult]
    search_time_ms: Optional[float]
    search_methods_used: List[str]
    suggestions: List[str] = []


class QuestionSuggestionResponse(BaseModel):
    suggestions: List[str]


@router.get("/", response_model=SearchResponse)
async def search_knowledge_base_get(
    request: Request,
    query: str = Query(..., min_length=1, max_length=500, description="Search query"),
    language: str = Query(default="auto", description="Language preference (auto, en, ar)"),
    category: Optional[str] = Query(default=None, description="Category filter"),
    scholar: Optional[str] = Query(default=None, description="Scholar filter"),
    source: Optional[str] = Query(default=None, description="Source filter"),
    use_ml: bool = Query(default=True, description="Use ML-powered search"),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum results"),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Search the Islamic Q&A knowledge base (GET method for frontend)"""
    # Create SearchRequest object from query parameters
    search_request = SearchRequest(
        query=query,
        language=language,
        category=category,
        scholar=scholar,
        source=source,
        use_ml=use_ml,
        limit=limit
    )
    
    return await search_knowledge_base_implementation(search_request, request, user, db)


@router.post("/", response_model=SearchResponse)
async def search_knowledge_base_post(
    search_request: SearchRequest,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Search the Islamic Q&A knowledge base (POST method)"""
    return await search_knowledge_base_implementation(search_request, request, user, db)


async def search_knowledge_base_implementation(
    search_request: SearchRequest,
    request: Request,
    user: Optional[User],
    db: Session
):
    """Search the Islamic Q&A knowledge base - shared implementation"""
    try:
        # Rate limiting
        if user:
            if not RateLimiter.check_rate_limit(str(user.id), user.rate_limit):
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
        else:
            # Anonymous rate limiting based on IP
            client_ip = request.client.host if request.client else "unknown"
            if not RateLimiter.check_rate_limit(f"ip:{client_ip}", 20):  # Lower limit for anonymous
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        # Initialize knowledge service
        knowledge_service = KnowledgeService()
        await knowledge_service.initialize()
        
        # Prepare filters
        filters = {}
        if search_request.category:
            filters['category'] = search_request.category
        if search_request.scholar:
            filters['scholar'] = search_request.scholar
        if search_request.source:
            filters['source'] = search_request.source
        
        # Perform search
        import time
        start_time = time.time()
        
        search_results = await knowledge_service.search_knowledge_base(
            query=search_request.query,
            language=search_request.language,
            filters=filters,
            use_ml=search_request.use_ml,
            limit=search_request.limit
        )
        
        search_time = (time.time() - start_time) * 1000
        
        # Convert to response format
        results = []
        for result in search_results.get('results', []):
            results.append(SearchResult(
                question_id=result.get('question_id', ''),
                question=result.get('question', ''),
                answer=result.get('answer', ''),
                similarity_score=result.get('similarity_score', 0.0),
                source_name=result.get('source_name', ''),
                source_url=result.get('source_url'),
                scholar_name=result.get('scholar_name'),
                category=result.get('category'),
                language=result.get('language', 'en'),
                confidence_score=result.get('confidence_score', 0.0),
                is_verified=result.get('is_verified', False)
            ))
        
        # Get suggestions for partial queries
        suggestions = []
        if len(search_request.query) >= 3:
            ml_service = MLService()
            suggestions = await ml_service.get_question_suggestions(
                search_request.query, 
                search_request.language
            )
        
        # Record user interaction
        session_id = str(uuid.uuid4())
        await knowledge_service.record_user_interaction(
            session_id=session_id,
            query=search_request.query,
            results=search_results.get('results', [])
        )
        
        # Record metrics
        MetricsCollector.record_question_asked(
            language=search_request.language,
            category=search_request.category or 'general'
        )
        
        return SearchResponse(
            query=search_request.query,
            language=search_request.language,
            total_results=search_results.get('total_results', 0),
            results=results,
            search_time_ms=search_time,
            search_methods_used=search_results.get('search_methods_used', []),
            suggestions=suggestions[:5]  # Limit suggestions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/suggestions", response_model=QuestionSuggestionResponse)
async def get_question_suggestions(
    q: str = Query(..., min_length=2, description="Partial query for suggestions"),
    language: str = Query(default="auto", description="Language preference"),
    limit: int = Query(default=10, ge=1, le=20, description="Maximum suggestions"),
    user: Optional[User] = Depends(get_optional_user)
):
    """Get question suggestions for autocomplete"""
    try:
        # Rate limiting for suggestions
        if user:
            if not RateLimiter.check_rate_limit(f"suggestions:{str(user.id)}", 50):
                raise HTTPException(status_code=429, detail="Too many suggestion requests")
        
        ml_service = MLService()
        await ml_service.initialize_models()
        
        suggestions = await ml_service.get_question_suggestions(q, language)
        
        return QuestionSuggestionResponse(
            suggestions=suggestions[:limit]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get suggestions: {str(e)}"
        )


@router.get("/categories")
async def get_categories(
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Get all available categories"""
    try:
        knowledge_service = KnowledgeService()
        categories = await knowledge_service.get_categories()
        
        return {
            "categories": categories,
            "total": len(categories)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get categories: {str(e)}"
        )


@router.get("/scholars")
async def get_scholars(
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Get all available scholars"""
    try:
        knowledge_service = KnowledgeService()
        scholars = await knowledge_service.get_scholars()
        
        return {
            "scholars": scholars,
            "total": len(scholars)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get scholars: {str(e)}"
        )


@router.get("/advanced")
async def advanced_search(
    q: str = Query(..., description="Search query"),
    language: str = Query(default="auto", description="Language filter"),
    category: Optional[str] = Query(default=None, description="Category filter"),
    scholar: Optional[str] = Query(default=None, description="Scholar filter"),
    source: Optional[str] = Query(default=None, description="Source filter"),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0, description="Minimum confidence score"),
    sort_by: str = Query(default="relevance", description="Sort order (relevance, date, confidence)"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Advanced search with multiple filters and sorting options"""
    try:
        # Rate limiting
        if user:
            if not RateLimiter.check_rate_limit(str(user.id), user.rate_limit):
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        knowledge_service = KnowledgeService()
        await knowledge_service.initialize()
        
        # Build filters
        filters = {}
        if language != "auto":
            filters['language'] = language
        if category:
            filters['category'] = category
        if scholar:
            filters['scholar'] = scholar
        if source:
            filters['source'] = source
        if min_confidence > 0:
            filters['min_confidence'] = min_confidence
        
        # Perform advanced search
        search_results = await knowledge_service.search_knowledge_base(
            query=q,
            language=language,
            filters=filters,
            use_ml=True,
            limit=limit
        )
        
        # Apply additional filtering and sorting
        results = search_results.get('results', [])
        
        # Filter by minimum confidence
        if min_confidence > 0:
            results = [r for r in results if r.get('confidence_score', 0) >= min_confidence]
        
        # Sort results
        if sort_by == "confidence":
            results.sort(key=lambda x: x.get('confidence_score', 0), reverse=True)
        elif sort_by == "date":
            # Would need date information in results
            pass
        # Default is relevance (already sorted)
        
        return {
            "query": q,
            "filters": filters,
            "sort_by": sort_by,
            "total_results": len(results),
            "results": results[:limit]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Advanced search failed: {str(e)}"
        )


@router.get("/similar/{question_id}")
async def find_similar_questions(
    question_id: str,
    limit: int = Query(default=10, ge=1, le=20, description="Maximum similar questions"),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Find questions similar to a specific question"""
    try:
        knowledge_service = KnowledgeService()
        await knowledge_service.initialize()
        
        # Get the original question
        original_question = await knowledge_service.get_question_by_id(question_id)
        if not original_question:
            raise HTTPException(status_code=404, detail="Question not found")
        
        # Find similar questions
        search_results = await knowledge_service.search_knowledge_base(
            query=original_question['question'],
            language=original_question['language'],
            use_ml=True,
            limit=limit + 1  # +1 to exclude the original
        )
        
        # Filter out the original question
        similar_questions = [
            result for result in search_results.get('results', [])
            if result.get('question_id') != question_id
        ][:limit]
        
        return {
            "original_question_id": question_id,
            "similar_questions": similar_questions,
            "total_found": len(similar_questions)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to find similar questions: {str(e)}"
        )


@router.post("/feedback")
async def submit_search_feedback(
    question_id: str,
    rating: int = Query(..., ge=1, le=5, description="Rating from 1-5"),
    comment: Optional[str] = Query(default=None, description="Optional feedback comment"),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Submit feedback for a search result"""
    try:
        knowledge_service = KnowledgeService()
        
        # Record feedback
        session_id = str(uuid.uuid4())
        feedback = {
            "rating": rating,
            "comment": comment
        }
        
        await knowledge_service.record_user_interaction(
            session_id=session_id,
            query="",  # Not tracking query for feedback
            results=[{"question_id": question_id}],
            feedback=feedback
        )
        
        return {
            "message": "Feedback submitted successfully",
            "question_id": question_id,
            "rating": rating
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit feedback: {str(e)}"
        )
