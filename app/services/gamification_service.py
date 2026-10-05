"""
Gamification Service
Streaks, hasanat (reward) tally, and leaderboard logic for the Quran
reading/recitation habit loop.

Hasanat is computed from the hadith (Tirmidhi) that each letter recited from
the Quran multiplies ten-fold in reward -- not an arbitrary point system.
Letter count is taken from the real `text_uthmani` corpus text (Phase 1),
diacritics stripped first (the same pyarabic normalization used elsewhere)
so a diacritic mark doesn't get counted as its own "letter".

No Redis sorted sets here: this project is explicitly demo-scale (see
rerank_service.py's framing), so a plain `ORDER BY` query is simpler, has
one source of truth, and is entirely sufficient at this scale.
"""

from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

import pyarabic.araby as araby
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import User, UserStreak
from app.services.quran_corpus_service import QuranCorpusService

HASANAT_PER_LETTER = 10
LEADERBOARD_METRICS = {"total_hasanat", "current_streak"}


class InvalidAyahRangeError(Exception):
    """Raised for an out-of-corpus or backwards ayah range."""


def _count_letters(text_uthmani: str) -> int:
    """Count recitable letters, excluding diacritics and whitespace."""
    stripped = araby.strip_diacritics(text_uthmani)
    return sum(1 for ch in stripped if not ch.isspace())


class GamificationService:
    def __init__(self, corpus_service: QuranCorpusService = None):
        self.corpus_service = corpus_service or QuranCorpusService()

    def _verses_in_range(self, surah: int, ayah_from: int, ayah_to: int) -> List[Dict[str, Any]]:
        if ayah_from > ayah_to:
            raise InvalidAyahRangeError("ayah_from must be <= ayah_to")

        self.corpus_service.load_or_fetch()
        verses = []
        for ayah_number in range(ayah_from, ayah_to + 1):
            ayah = self.corpus_service.get_ayah(surah, ayah_number)
            if not ayah:
                raise InvalidAyahRangeError(f"Ayah {surah}:{ayah_number} not found")
            verses.append(ayah)
        return verses

    def log_progress(
        self, db: Session, user_id: str, surah: int, ayah_from: int, ayah_to: int
    ) -> UserStreak:
        """Record a reading/recitation session, updating streak + hasanat."""
        verses = self._verses_in_range(surah, ayah_from, ayah_to)
        verses_count = len(verses)
        hasanat = sum(_count_letters(v["text_uthmani"]) for v in verses) * HASANAT_PER_LETTER

        streak = db.query(UserStreak).filter(UserStreak.user_id == user_id).first()
        if streak is None:
            streak = UserStreak(user_id=user_id, current_streak=0, longest_streak=0,
                                 total_verses_read=0, total_hasanat=0)
            db.add(streak)

        today = date.today()
        if streak.last_activity_date is None or streak.last_activity_date < today - timedelta(days=1):
            streak.current_streak = 1
        elif streak.last_activity_date == today - timedelta(days=1):
            streak.current_streak += 1
        # else: last_activity_date == today -- same-day logging, streak unchanged

        streak.longest_streak = max(streak.longest_streak, streak.current_streak)
        streak.last_activity_date = today
        streak.total_verses_read += verses_count
        streak.total_hasanat += hasanat

        db.commit()
        db.refresh(streak)
        return streak

    def get_streak(self, db: Session, user_id: str) -> UserStreak:
        streak = db.query(UserStreak).filter(UserStreak.user_id == user_id).first()
        if streak is None:
            return UserStreak(user_id=user_id, current_streak=0, longest_streak=0,
                               last_activity_date=None, total_verses_read=0, total_hasanat=0)
        return streak

    def get_leaderboard(
        self, db: Session, metric: str = "total_hasanat", limit: int = 20
    ) -> List[Tuple[UserStreak, User]]:
        if metric not in LEADERBOARD_METRICS:
            raise ValueError(f"metric must be one of {LEADERBOARD_METRICS}")

        return (
            db.query(UserStreak, User)
            .join(User, UserStreak.user_id == User.id)
            .order_by(desc(getattr(UserStreak, metric)))
            .limit(limit)
            .all()
        )


gamification_service = GamificationService()
