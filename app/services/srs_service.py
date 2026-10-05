"""
Spaced Repetition (SM-2) Service
Standard SM-2 scheduling for hifz (memorization) practice -- not FSRS: FSRS
fits its forgetting-curve model from a large review-history dataset, which
doesn't exist yet for a brand-new product. SM-2 is well-understood and
needs no training data.

A card's review can be graded two ways: a direct `quality` (0-5, SM-2's
native scale) or derived from a Phase 2 recitation-check's mistake count
via `quality_from_mistake_count` -- the "driven by actual recitation-test
results" differentiator from the roadmap, rather than pure self-rating.
"""

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import MemorizationCard

MIN_EASE_FACTOR = 1.3
DEFAULT_EASE_FACTOR = 2.5

# Tiered mapping from a recitation-check's mistake count to SM-2's 0-5
# quality scale. Deliberately simple -- tunable later once real usage data
# exists to calibrate against.
_MISTAKE_COUNT_TO_QUALITY = [
    (0, 5),
    (1, 4),
    (2, 3),
    (4, 2),  # 3-4 mistakes
]
_MIN_QUALITY_FOR_MANY_MISTAKES = 1


def quality_from_mistake_count(mistake_count: int) -> int:
    """Map a recitation-check mistake count to an SM-2 quality grade (0-5)."""
    for max_mistakes, quality in _MISTAKE_COUNT_TO_QUALITY:
        if mistake_count <= max_mistakes:
            return quality
    return _MIN_QUALITY_FOR_MANY_MISTAKES


def grade_review(card: MemorizationCard, quality: int) -> MemorizationCard:
    """Apply the standard SM-2 update to `card` in place and return it.

    quality < 3 means the recall failed: repetitions and interval reset,
    and it'll be shown again tomorrow. quality >= 3 progresses the normal
    SM-2 interval sequence (1 day -> 6 days -> previous_interval * ease_factor)
    and nudges ease_factor per SM-2's standard formula.
    """
    if not 0 <= quality <= 5:
        raise ValueError("quality must be between 0 and 5")

    if quality < 3:
        card.repetitions = 0
        card.interval_days = 1
    else:
        if card.repetitions == 0:
            card.interval_days = 1
        elif card.repetitions == 1:
            card.interval_days = 6
        else:
            card.interval_days = round(card.interval_days * card.ease_factor)
        card.repetitions += 1

    card.ease_factor = max(
        MIN_EASE_FACTOR,
        card.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
    )

    card.last_reviewed_at = datetime.utcnow()
    card.due_date = date.today() + timedelta(days=card.interval_days)
    return card


def get_or_create_card(db: Session, user_id: str, surah: int, ayah: int) -> MemorizationCard:
    card = (
        db.query(MemorizationCard)
        .filter(
            MemorizationCard.user_id == user_id,
            MemorizationCard.surah_number == surah,
            MemorizationCard.ayah_number == ayah,
        )
        .first()
    )
    if card is None:
        card = MemorizationCard(
            user_id=user_id, surah_number=surah, ayah_number=ayah,
            ease_factor=DEFAULT_EASE_FACTOR, interval_days=0, repetitions=0,
            due_date=date.today(),
        )
        db.add(card)
        db.commit()
        db.refresh(card)
    return card


def get_card(db: Session, user_id: str, surah: int, ayah: int) -> Optional[MemorizationCard]:
    return (
        db.query(MemorizationCard)
        .filter(
            MemorizationCard.user_id == user_id,
            MemorizationCard.surah_number == surah,
            MemorizationCard.ayah_number == ayah,
        )
        .first()
    )


def get_due_cards(db: Session, user_id: str, limit: int = 20):
    return (
        db.query(MemorizationCard)
        .filter(MemorizationCard.user_id == user_id, MemorizationCard.due_date <= date.today())
        .order_by(MemorizationCard.due_date)
        .limit(limit)
        .all()
    )
