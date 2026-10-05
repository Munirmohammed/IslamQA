"""
Gamification Endpoints
Streaks, hasanat tally, and a global leaderboard for the Quran reading/
recitation habit loop.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import User, get_db
from app.core.security import get_current_user, get_optional_user
from app.services.gamification_service import (
    InvalidAyahRangeError,
    LEADERBOARD_METRICS,
    gamification_service,
)

router = APIRouter()


class LogProgressRequest(BaseModel):
    surah: int = Field(..., ge=1, le=114)
    ayah_from: int = Field(..., ge=1)
    ayah_to: int = Field(..., ge=1)


class StreakResponse(BaseModel):
    current_streak: int
    longest_streak: int
    last_activity_date: Optional[str]
    total_verses_read: int
    total_hasanat: int


def _to_streak_response(streak) -> StreakResponse:
    return StreakResponse(
        current_streak=streak.current_streak,
        longest_streak=streak.longest_streak,
        last_activity_date=streak.last_activity_date.isoformat() if streak.last_activity_date else None,
        total_verses_read=streak.total_verses_read,
        total_hasanat=streak.total_hasanat,
    )


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    current_streak: int
    total_hasanat: int


class LeaderboardResponse(BaseModel):
    metric: str
    entries: List[LeaderboardEntry]


@router.post("/log-progress", response_model=StreakResponse)
async def log_progress(
    request: LogProgressRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record a reading/recitation session, updating the user's streak and hasanat."""
    try:
        streak = gamification_service.log_progress(
            db, user_id=user.id, surah=request.surah,
            ayah_from=request.ayah_from, ayah_to=request.ayah_to,
        )
        return _to_streak_response(streak)
    except InvalidAyahRangeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me", response_model=StreakResponse)
async def get_my_streak(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's streak/hasanat stats."""
    streak = gamification_service.get_streak(db, user_id=user.id)
    return _to_streak_response(streak)


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    metric: str = Query(default="total_hasanat", description=f"One of {sorted(LEADERBOARD_METRICS)}"),
    limit: int = Query(default=20, ge=1, le=100),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Global leaderboard, ranked by the given metric."""
    if metric not in LEADERBOARD_METRICS:
        raise HTTPException(status_code=400, detail=f"metric must be one of {sorted(LEADERBOARD_METRICS)}")

    rows = gamification_service.get_leaderboard(db, metric=metric, limit=limit)
    entries = [
        LeaderboardEntry(
            rank=i + 1,
            username=user_row.username,
            current_streak=streak_row.current_streak,
            total_hasanat=streak_row.total_hasanat,
        )
        for i, (streak_row, user_row) in enumerate(rows)
    ]
    return LeaderboardResponse(metric=metric, entries=entries)
