"""
SRS (SM-2) Service Tests
Covers the standard SM-2 reference sequence as a pure function over
MemorizationCard fields (no DB needed for grade_review itself), plus the
mistake-count-to-quality tiering and the DB-backed due-card/get-or-create
helpers.
"""

from datetime import date, timedelta

import pytest

from app.core.database import MemorizationCard, User
from app.services import srs_service


def _new_card(**overrides):
    defaults = dict(
        user_id="u1", surah_number=1, ayah_number=1,
        ease_factor=2.5, interval_days=0, repetitions=0, due_date=date.today(),
    )
    defaults.update(overrides)
    return MemorizationCard(**defaults)


class TestQualityFromMistakeCount:
    @pytest.mark.parametrize("mistakes,expected_quality", [
        (0, 5), (1, 4), (2, 3), (3, 2), (4, 2), (5, 1), (100, 1),
    ])
    def test_tiering(self, mistakes, expected_quality):
        assert srs_service.quality_from_mistake_count(mistakes) == expected_quality


class TestGradeReviewRejectsOutOfRangeQuality:
    def test_rejects_quality_above_five(self):
        with pytest.raises(ValueError):
            srs_service.grade_review(_new_card(), quality=6)

    def test_rejects_negative_quality(self):
        with pytest.raises(ValueError):
            srs_service.grade_review(_new_card(), quality=-1)


class TestGradeReviewSM2Sequence:
    """The standard SM-2 reference sequence: perfect recalls (quality=5)
    progress intervals 1 -> 6 -> interval*ease_factor, each repetition
    nudging ease_factor upward."""

    def test_first_perfect_review_sets_interval_to_one_day(self):
        card = _new_card()
        srs_service.grade_review(card, quality=5)
        assert card.interval_days == 1
        assert card.repetitions == 1
        assert card.due_date == date.today() + timedelta(days=1)

    def test_second_perfect_review_sets_interval_to_six_days(self):
        card = _new_card()
        srs_service.grade_review(card, quality=5)
        srs_service.grade_review(card, quality=5)
        assert card.interval_days == 6
        assert card.repetitions == 2

    def test_third_perfect_review_multiplies_by_ease_factor(self):
        card = _new_card()
        srs_service.grade_review(card, quality=5)  # interval=1
        srs_service.grade_review(card, quality=5)  # interval=6
        ease_after_two = card.ease_factor
        srs_service.grade_review(card, quality=5)  # interval=6*ease
        assert card.interval_days == round(6 * ease_after_two)
        assert card.repetitions == 3

    def test_ease_factor_increases_with_perfect_reviews(self):
        card = _new_card()
        srs_service.grade_review(card, quality=5)
        assert card.ease_factor > 2.5

    def test_failed_review_resets_repetitions_and_interval(self):
        card = _new_card()
        srs_service.grade_review(card, quality=5)
        srs_service.grade_review(card, quality=5)
        assert card.repetitions == 2

        srs_service.grade_review(card, quality=1)  # failed recall
        assert card.repetitions == 0
        assert card.interval_days == 1
        assert card.due_date == date.today() + timedelta(days=1)

    def test_ease_factor_never_drops_below_minimum(self):
        card = _new_card(ease_factor=1.3)
        for _ in range(10):
            srs_service.grade_review(card, quality=0)
        assert card.ease_factor >= srs_service.MIN_EASE_FACTOR


class TestDueCardsAndGetOrCreate:
    @pytest.fixture
    def test_user(self, db_session):
        import uuid
        unique = uuid.uuid4().hex[:8]
        user = User(username=f"srs-{unique}", email=f"srs-{unique}@example.com", hashed_password="x")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    def test_get_or_create_is_idempotent(self, db_session, test_user):
        card1 = srs_service.get_or_create_card(db_session, test_user.id, 1, 1)
        card2 = srs_service.get_or_create_card(db_session, test_user.id, 1, 1)
        assert card1.id == card2.id

    def test_due_cards_excludes_future_due_dates(self, db_session, test_user):
        due_today = srs_service.get_or_create_card(db_session, test_user.id, 1, 1)

        not_due_card = srs_service.get_or_create_card(db_session, test_user.id, 1, 2)
        not_due_card.due_date = date.today() + timedelta(days=5)
        db_session.commit()

        due = srs_service.get_due_cards(db_session, test_user.id, limit=20)
        due_ayah_numbers = {c.ayah_number for c in due}

        assert 1 in due_ayah_numbers
        assert 2 not in due_ayah_numbers
