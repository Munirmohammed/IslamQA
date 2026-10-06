"""
Halaqa (Teacher/Student Circle) Endpoints
A teacher dashboard for reviewing students' recitation-check history
(Phase 2), with auto-generated mistake summaries -- grading that scales
beyond 1:1 listening.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import User, get_db
from app.core.security import get_current_user
from app.services import halaqa_service
from app.services.halaqa_service import HalaqaNotFoundError, InvalidJoinCodeError

router = APIRouter()


class CreateHalaqaRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class JoinHalaqaRequest(BaseModel):
    join_code: str


class HalaqaResponse(BaseModel):
    id: str
    name: str
    join_code: str
    created_at: str


def _to_halaqa_response(halaqa) -> HalaqaResponse:
    return HalaqaResponse(
        id=halaqa.id, name=halaqa.name, join_code=halaqa.join_code,
        created_at=halaqa.created_at.isoformat(),
    )


class MyHalaqasResponse(BaseModel):
    teaching: List[HalaqaResponse]
    studying: List[HalaqaResponse]


class StudentSummary(BaseModel):
    student_id: str
    username: str
    joined_at: str
    session_count: int
    correct_count: int
    correct_rate: Optional[float]


class Mistake(BaseModel):
    type: str
    expected: str
    recited: str
    position: int


class StudentSession(BaseModel):
    session_id: str
    surah_number: int
    ayah_number: int
    transcript: str
    mistake_count: int
    is_correct: bool
    is_duplicate_submission: bool
    created_at: str
    mistakes: List[Mistake]


def _require_teacher(db: Session, halaqa_id: str, user: User):
    """Looks up the halaqa and raises 404/403 as appropriate. Returns the
    halaqa on success."""
    try:
        halaqa = halaqa_service.get_halaqa_or_raise(db, halaqa_id)
    except HalaqaNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if halaqa.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Only this halaqa's teacher can do that")
    return halaqa


@router.post("/create", response_model=HalaqaResponse)
async def create_halaqa(
    request: CreateHalaqaRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    halaqa = halaqa_service.create_halaqa(db, teacher_id=user.id, name=request.name)
    return _to_halaqa_response(halaqa)


@router.post("/join")
async def join_halaqa(
    request: JoinHalaqaRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        membership = halaqa_service.join_halaqa(db, student_id=user.id, join_code=request.join_code)
    except InvalidJoinCodeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"halaqa_id": membership.halaqa_id, "joined_at": membership.joined_at.isoformat()}


@router.get("/mine", response_model=MyHalaqasResponse)
async def get_my_halaqas(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    halaqas = halaqa_service.get_my_halaqas(db, user_id=user.id)
    return MyHalaqasResponse(
        teaching=[_to_halaqa_response(h) for h in halaqas["teaching"]],
        studying=[_to_halaqa_response(h) for h in halaqas["studying"]],
    )


@router.get("/{halaqa_id}/students", response_model=List[StudentSummary])
async def get_halaqa_students(
    halaqa_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Teacher-only: each student's summary stats."""
    _require_teacher(db, halaqa_id, user)
    summaries = halaqa_service.get_student_summaries(db, halaqa_id)
    return [
        StudentSummary(**{**s, "joined_at": s["joined_at"].isoformat()})
        for s in summaries
    ]


@router.get("/{halaqa_id}/students/{student_id}/sessions", response_model=List[StudentSession])
async def get_student_sessions(
    halaqa_id: str,
    student_id: str,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Teacher-only: a specific student's recitation-check history with
    mistake details -- the auto-generated mistake summaries a teacher
    dashboard needs to grade beyond 1:1 listening."""
    _require_teacher(db, halaqa_id, user)

    if not halaqa_service.is_student_of(db, halaqa_id, student_id):
        raise HTTPException(status_code=404, detail="That student isn't a member of this halaqa")

    sessions = halaqa_service.get_student_sessions(db, student_id, limit=limit)
    return [
        StudentSession(**{**s, "created_at": s["created_at"].isoformat()})
        for s in sessions
    ]
