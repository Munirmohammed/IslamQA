"""
Questions Endpoints
CRUD operations for questions and answers
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import datetime

from app.core.database import get_db, Question, Answer, User
from app.core.security import get_current_user, get_current_admin_user, get_optional_user
from app.services.knowledge_service import KnowledgeService

router = APIRouter()


class QuestionResponse(BaseModel):
    question_id: str
    question: str
    category: Optional[str]
    language: str
    tags: List[str]
    created_at: str
    answers: List[dict]


class AnswerResponse(BaseModel):
    answer_id: str
    answer_text: str
    source_name: str
    source_url: Optional[str]
    scholar_name: Optional[str]
    confidence_score: float
    is_verified: bool
    references: dict
    created_at: str


class QuestionCreate(BaseModel):
    question_text: str = Field(..., min_length=10, max_length=1000)
    category: Optional[str] = None
    language: str = Field(default="en")
    tags: List[str] = Field(default=[])


class AnswerCreate(BaseModel):
    answer_text: str = Field(..., min_length=20)
    source_name: str
    source_url: Optional[str] = None
    scholar_name: Optional[str] = None
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    is_verified: bool = Field(default=False)
    references: dict = Field(default={})


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(
    question_id: str,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Get a specific question and its answers"""
    try:
        knowledge_service = KnowledgeService()
        question_data = await knowledge_service.get_question_by_id(question_id)
        
        if not question_data:
            raise HTTPException(status_code=404, detail="Question not found")
        
        return QuestionResponse(**question_data)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get question: {str(e)}"
        )


@router.get("/", response_model=List[QuestionResponse])
async def list_questions(
    skip: int = Query(default=0, ge=0, description="Number of questions to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum questions to return"),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    language: Optional[str] = Query(default=None, description="Filter by language"),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """List questions with optional filters"""
    try:
        query = db.query(Question)
        
        # Apply filters
        if category:
            query = query.filter(Question.category == category)
        if language:
            query = query.filter(Question.language == language)
        
        # Get questions with pagination
        questions = query.offset(skip).limit(limit).all()
        
        # Get answers for each question
        result = []
        for question in questions:
            answers = db.query(Answer).filter(
                Answer.question_id == question.id
            ).order_by(Answer.confidence_score.desc()).all()
            
            answer_list = []
            for answer in answers:
                answer_list.append({
                    "answer_id": str(answer.id),
                    "answer_text": answer.answer_text,
                    "source_name": answer.source_name,
                    "source_url": answer.source_url,
                    "scholar_name": answer.scholar_name,
                    "confidence_score": answer.confidence_score,
                    "is_verified": answer.is_verified,
                    "references": answer.references or {},
                    "created_at": answer.created_at.isoformat() if answer.created_at else None
                })
            
            result.append(QuestionResponse(
                question_id=str(question.id),
                question=question.question_text,
                category=question.category,
                language=question.language,
                tags=question.tags or [],
                created_at=question.created_at.isoformat() if question.created_at else None,
                answers=answer_list
            ))
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list questions: {str(e)}"
        )


@router.post("/", response_model=QuestionResponse)
async def create_question(
    question_data: QuestionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new question (authenticated users only)"""
    try:
        from app.core.security import SecurityUtils
        
        # Generate question hash for deduplication
        question_hash = SecurityUtils.hash_string(question_data.question_text)
        
        # Check for duplicate
        existing = db.query(Question).filter(Question.question_hash == question_hash).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail="A similar question already exists"
            )
        
        # Create question
        question = Question(
            question_text=question_data.question_text,
            question_hash=question_hash,
            category=question_data.category,
            language=question_data.language,
            tags=question_data.tags,
            created_at=datetime.utcnow()
        )
        
        db.add(question)
        db.commit()
        db.refresh(question)
        
        return QuestionResponse(
            question_id=str(question.id),
            question=question.question_text,
            category=question.category,
            language=question.language,
            tags=question.tags or [],
            created_at=question.created_at.isoformat(),
            answers=[]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create question: {str(e)}"
        )


@router.post("/{question_id}/answers", response_model=AnswerResponse)
async def add_answer(
    question_id: str,
    answer_data: AnswerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add an answer to a question (authenticated users only)"""
    try:
        # Check if question exists
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        
        # Create answer
        answer = Answer(
            question_id=question.id,
            answer_text=answer_data.answer_text,
            source_name=answer_data.source_name,
            source_url=answer_data.source_url,
            scholar_name=answer_data.scholar_name,
            confidence_score=answer_data.confidence_score,
            is_verified=answer_data.is_verified and current_user.is_admin,  # Only admins can mark as verified
            references=answer_data.references,
            created_at=datetime.utcnow()
        )
        
        db.add(answer)
        db.commit()
        db.refresh(answer)
        
        return AnswerResponse(
            answer_id=str(answer.id),
            answer_text=answer.answer_text,
            source_name=answer.source_name,
            source_url=answer.source_url,
            scholar_name=answer.scholar_name,
            confidence_score=answer.confidence_score,
            is_verified=answer.is_verified,
            references=answer.references or {},
            created_at=answer.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add answer: {str(e)}"
        )


@router.put("/{question_id}")
async def update_question(
    question_id: str,
    question_data: QuestionCreate,
    current_user: User = Depends(get_current_admin_user),  # Admin only
    db: Session = Depends(get_db)
):
    """Update a question (admin only)"""
    try:
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        
        # Update fields
        question.question_text = question_data.question_text
        question.category = question_data.category
        question.language = question_data.language
        question.tags = question_data.tags
        question.updated_at = datetime.utcnow()
        
        # Update hash
        from app.core.security import SecurityUtils
        question.question_hash = SecurityUtils.hash_string(question_data.question_text)
        
        db.commit()
        
        return {"message": "Question updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update question: {str(e)}"
        )


@router.delete("/{question_id}")
async def delete_question(
    question_id: str,
    current_user: User = Depends(get_current_admin_user),  # Admin only
    db: Session = Depends(get_db)
):
    """Delete a question and its answers (admin only)"""
    try:
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        
        # Delete associated answers first
        db.query(Answer).filter(Answer.question_id == question.id).delete()
        
        # Delete question
        db.delete(question)
        db.commit()
        
        return {"message": "Question deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete question: {str(e)}"
        )


@router.put("/answers/{answer_id}")
async def update_answer(
    answer_id: str,
    answer_data: AnswerCreate,
    current_user: User = Depends(get_current_admin_user),  # Admin only
    db: Session = Depends(get_db)
):
    """Update an answer (admin only)"""
    try:
        answer = db.query(Answer).filter(Answer.id == answer_id).first()
        if not answer:
            raise HTTPException(status_code=404, detail="Answer not found")
        
        # Update fields
        answer.answer_text = answer_data.answer_text
        answer.source_name = answer_data.source_name
        answer.source_url = answer_data.source_url
        answer.scholar_name = answer_data.scholar_name
        answer.confidence_score = answer_data.confidence_score
        answer.is_verified = answer_data.is_verified
        answer.references = answer_data.references
        answer.updated_at = datetime.utcnow()
        
        db.commit()
        
        return {"message": "Answer updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update answer: {str(e)}"
        )


@router.delete("/answers/{answer_id}")
async def delete_answer(
    answer_id: str,
    current_user: User = Depends(get_current_admin_user),  # Admin only
    db: Session = Depends(get_db)
):
    """Delete an answer (admin only)"""
    try:
        answer = db.query(Answer).filter(Answer.id == answer_id).first()
        if not answer:
            raise HTTPException(status_code=404, detail="Answer not found")
        
        db.delete(answer)
        db.commit()
        
        return {"message": "Answer deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete answer: {str(e)}"
        )


@router.get("/{question_id}/related")
async def get_related_questions(
    question_id: str,
    limit: int = Query(default=10, ge=1, le=20),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Get questions related to a specific question"""
    try:
        knowledge_service = KnowledgeService()
        
        # Get the original question
        question_data = await knowledge_service.get_question_by_id(question_id)
        if not question_data:
            raise HTTPException(status_code=404, detail="Question not found")
        
        # Find similar questions using ML
        search_results = await knowledge_service.search_knowledge_base(
            query=question_data['question'],
            language=question_data['language'],
            use_ml=True,
            limit=limit + 1  # +1 to exclude original
        )
        
        # Filter out the original question
        related_questions = [
            result for result in search_results.get('results', [])
            if result.get('question_id') != question_id
        ][:limit]
        
        return {
            "question_id": question_id,
            "related_questions": related_questions,
            "total_found": len(related_questions)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get related questions: {str(e)}"
        )
