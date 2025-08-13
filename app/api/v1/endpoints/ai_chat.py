"""
AI Chat Endpoints
Simple conversational AI endpoints replacing complex knowledge base
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

from app.core.database import get_db, User, UserInteraction
from app.core.security import get_optional_user, RateLimiter
from app.services.simple_ai_service import simple_ai_service
from app.core.monitoring import MetricsCollector

router = APIRouter()


class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., min_length=1, max_length=2000, description="Message content")
    timestamp: Optional[str] = Field(default=None, description="Message timestamp")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="User message")
    language: str = Field(default="auto", description="Language preference (auto, en, ar)")
    conversation_history: List[ChatMessage] = Field(default=[], description="Previous messages in conversation")
    session_id: Optional[str] = Field(default=None, description="Session ID for tracking")


class ChatResponse(BaseModel):
    response: str
    language: str
    confidence: float
    source: str
    timestamp: str
    session_id: str
    service_used: str


class SimpleSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    language: str = Field(default="auto", description="Language preference (auto, en, ar)")


class SimpleSearchResponse(BaseModel):
    query: str
    answer: str
    language: str
    confidence: float
    source: str
    timestamp: str
    response_time_ms: float


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    chat_request: ChatRequest,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Chat with AI assistant - conversational interface"""
    try:
        # Rate limiting
        if user:
            if not RateLimiter.check_rate_limit(str(user.id), user.rate_limit):
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
        else:
            # Anonymous rate limiting based on IP
            client_ip = request.client.host if request.client else "unknown"
            if not RateLimiter.check_rate_limit(f"ip:{client_ip}", 30):  # 30 requests per hour for anonymous
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        # Generate session ID if not provided
        session_id = chat_request.session_id or str(uuid.uuid4())
        
        # Prepare conversation history
        messages = []
        for msg in chat_request.conversation_history:
            messages.append({
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp
            })
        
        # Add current message
        messages.append({
            "role": "user",
            "content": chat_request.message,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Get AI response
        import time
        start_time = time.time()
        
        ai_response = await simple_ai_service.get_conversation_response(
            messages=messages,
            language=chat_request.language
        )
        
        response_time = (time.time() - start_time) * 1000
        
        # Log interaction to database
        try:
            interaction = UserInteraction(
                session_id=session_id,
                user_query=chat_request.message,
                matched_answers=[ai_response],
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", ""),
                created_at=datetime.utcnow()
            )
            db.add(interaction)
            db.commit()
        except Exception as e:
            # Don't fail the request if logging fails
            print(f"Failed to log interaction: {e}")
        
        # Record metrics
        MetricsCollector.record_question_asked(
            ai_response.get('language', 'en'), 
            'ai_chat'
        )
        
        return ChatResponse(
            response=ai_response["answer"],
            language=ai_response["language"],
            confidence=ai_response["confidence"],
            source=ai_response["source"],
            timestamp=ai_response["timestamp"],
            session_id=session_id,
            service_used=ai_response.get("service", "ai")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get AI response: {str(e)}"
        )


@router.post("/simple-search", response_model=SimpleSearchResponse)
async def simple_search(
    search_request: SimpleSearchRequest,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Simple AI-powered search - direct question answering"""
    try:
        # Rate limiting
        if user:
            if not RateLimiter.check_rate_limit(str(user.id), user.rate_limit):
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
        else:
            client_ip = request.client.host if request.client else "unknown"
            if not RateLimiter.check_rate_limit(f"ip:{client_ip}", 25):
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        # Get AI response
        import time
        start_time = time.time()
        
        ai_response = await simple_ai_service.get_ai_response(
            question=search_request.query,
            language=search_request.language
        )
        
        response_time = (time.time() - start_time) * 1000
        
        # Log interaction
        try:
            interaction = UserInteraction(
                session_id=str(uuid.uuid4()),
                user_query=search_request.query,
                matched_answers=[ai_response],
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", ""),
                created_at=datetime.utcnow()
            )
            db.add(interaction)
            db.commit()
        except Exception as e:
            print(f"Failed to log interaction: {e}")
        
        return SimpleSearchResponse(
            query=search_request.query,
            answer=ai_response["answer"],
            language=ai_response["language"],
            confidence=ai_response["confidence"],
            source=ai_response["source"],
            timestamp=ai_response["timestamp"],
            response_time_ms=response_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process search: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """Check if AI service is available"""
    try:
        is_available = simple_ai_service.is_available()
        
        return {
            "status": "healthy" if is_available else "degraded",
            "ai_service_available": is_available,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "ai_service_available": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/session/{session_id}/history")
async def get_chat_history(
    session_id: str,
    limit: int = 50,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Get chat history for a session"""
    try:
        # Get interactions for this session
        interactions = db.query(UserInteraction).filter(
            UserInteraction.session_id == session_id
        ).order_by(UserInteraction.created_at.desc()).limit(limit).all()
        
        history = []
        for interaction in reversed(interactions):  # Reverse to get chronological order
            # Add user message
            history.append({
                "role": "user",
                "content": interaction.user_query,
                "timestamp": interaction.created_at.isoformat() if interaction.created_at else None
            })
            
            # Add AI response if available
            if interaction.matched_answers:
                try:
                    ai_answer = interaction.matched_answers[0] if isinstance(interaction.matched_answers, list) else interaction.matched_answers
                    if isinstance(ai_answer, dict) and "answer" in ai_answer:
                        history.append({
                            "role": "assistant", 
                            "content": ai_answer["answer"],
                            "timestamp": ai_answer.get("timestamp")
                        })
                except:
                    pass
        
        return {
            "session_id": session_id,
            "total_messages": len(history),
            "history": history
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get chat history: {str(e)}"
        )


@router.delete("/session/{session_id}")
async def clear_session(
    session_id: str,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Clear chat history for a session"""
    try:
        # Delete interactions for this session
        deleted_count = db.query(UserInteraction).filter(
            UserInteraction.session_id == session_id
        ).delete()
        
        db.commit()
        
        return {
            "message": f"Cleared {deleted_count} messages from session",
            "session_id": session_id
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear session: {str(e)}"
        )
