"""
Gamification Service Tests
Covers hasanat arithmetic, the three streak transitions (same-day,
consecutive-day, gap), and leaderboard ordering -- using a tiny in-memory
ayah corpus (no network/real-corpus dependency) and a fake "today" so streak
logic doesn't depend on real wall-clock dates.
"""

import uuid
from datetime import date, timedelta

import pytest

from app.core.database import User
from app.services.gamification_service import (
    GamificationService,
    InvalidAyahRangeError,
    _count_letters,
)
from app.services.quran_corpus_service import QuranCorpusService

FIXTURE_AYAHS = [
    {"key": "112:1", "surah_number": 112, "ayah_number": 1, "text_uthmani": "قُلْ هُوَ اللَّهُ أَحَدٌ", "text_simple": "قل هو الله احد"},
    {"key": "112:2", "surah_number": 112, "ayah_number": 2, "text_uthmani": "اللَّهُ الصَّمَدُ", "text_simple": "الله الصمد"},
    {"key": "112:3", "surah_number": 112, "ayah_number": 3, "text_uthmani": "لَمْ يَلِدْ وَلَمْ يُولَدْ", "text_simple": "لم يلد ولم يولد"},
]


class FakeCorpusService(QuranCorpusService):
    """A QuranCorpusService that serves the fixture ayahs above without
    touching disk or network."""

    def __init__(self):
        super().__init__(corpus_path="unused")
        self.ayahs = FIXTURE_AYAHS
        self._index_by_key()

    def load_or_fetch(self, force_refetch: bool = False):
        return self.ayahs


@pytest.fixture
def service():
    return GamificationService(corpus_service=FakeCorpusService())


def _make_user(db_session, label: str) -> User:
    """db_session commits persist to the shared test DB across the whole
    suite (see conftest.py), so usernames/emails must be unique per call,
    not just per test function."""
    unique = uuid.uuid4().hex[:8]
    user = User(username=f"{label}-{unique}", email=f"{label}-{unique}@example.com", hashed_password="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user(db_session):
    return _make_user(db_session, "gamify-user")


class TestCountLetters:
    def test_counts_non_space_characters_excluding_diacritics(self):
        assert _count_letters("اب") == 2
        assert _count_letters("أَحَدٌ") == 3  # 3 letters, diacritics stripped
        assert _count_letters("قل هو") == 4  # space not counted


class TestLogProgressHasanat:
    def test_hasanat_matches_letter_count_times_ten(self, service, db_session, test_user):
        streak = service.log_progress(db_session, test_user.id, surah=112, ayah_from=1, ayah_to=1)
        expected = _count_letters(FIXTURE_AYAHS[0]["text_uthmani"]) * 10
        assert streak.total_hasanat == expected
        assert streak.total_verses_read == 1

    def test_hasanat_accumulates_across_multiple_ayahs(self, service, db_session, test_user):
        streak = service.log_progress(db_session, test_user.id, surah=112, ayah_from=1, ayah_to=3)
        expected = sum(_count_letters(a["text_uthmani"]) for a in FIXTURE_AYAHS) * 10
        assert streak.total_hasanat == expected
        assert streak.total_verses_read == 3

    def test_invalid_range_raises(self, service, db_session, test_user):
        with pytest.raises(InvalidAyahRangeError):
            service.log_progress(db_session, test_user.id, surah=112, ayah_from=3, ayah_to=1)

        with pytest.raises(InvalidAyahRangeError):
            service.log_progress(db_session, test_user.id, surah=112, ayah_from=1, ayah_to=99)


class TestStreakTransitions:
    def test_first_ever_log_starts_streak_at_one(self, service, db_session, test_user, monkeypatch):
        monkeypatch.setattr("app.services.gamification_service.date",
                             type("FakeDate", (date,), {"today": staticmethod(lambda: date(2026, 1, 10))}))
        streak = service.log_progress(db_session, test_user.id, surah=112, ayah_from=1, ayah_to=1)
        assert streak.current_streak == 1
        assert streak.longest_streak == 1

    def test_same_day_second_log_does_not_increment_streak(self, service, db_session, test_user, monkeypatch):
        fake_today = date(2026, 1, 10)
        monkeypatch.setattr("app.services.gamification_service.date",
                             type("FakeDate", (date,), {"today": staticmethod(lambda: fake_today)}))

        service.log_progress(db_session, test_user.id, surah=112, ayah_from=1, ayah_to=1)
        streak = service.log_progress(db_session, test_user.id, surah=112, ayah_from=2, ayah_to=2)

        assert streak.current_streak == 1
        assert streak.total_verses_read == 2  # verses still accumulate

    def test_consecutive_day_increments_streak(self, service, db_session, test_user, monkeypatch):
        day1, day2 = date(2026, 1, 10), date(2026, 1, 11)

        monkeypatch.setattr("app.services.gamification_service.date",
                             type("FakeDate", (date,), {"today": staticmethod(lambda: day1)}))
        service.log_progress(db_session, test_user.id, surah=112, ayah_from=1, ayah_to=1)

        monkeypatch.setattr("app.services.gamification_service.date",
                             type("FakeDate", (date,), {"today": staticmethod(lambda: day2)}))
        streak = service.log_progress(db_session, test_user.id, surah=112, ayah_from=2, ayah_to=2)

        assert streak.current_streak == 2
        assert streak.longest_streak == 2

    def test_gap_of_more_than_one_day_resets_streak(self, service, db_session, test_user, monkeypatch):
        day1, day_much_later = date(2026, 1, 10), date(2026, 1, 20)

        monkeypatch.setattr("app.services.gamification_service.date",
                             type("FakeDate", (date,), {"today": staticmethod(lambda: day1)}))
        service.log_progress(db_session, test_user.id, surah=112, ayah_from=1, ayah_to=1)
        service.log_progress(db_session, test_user.id, surah=112, ayah_from=2, ayah_to=2)  # same day, still streak=1

        monkeypatch.setattr("app.services.gamification_service.date",
                             type("FakeDate", (date,), {"today": staticmethod(lambda: day_much_later)}))
        streak = service.log_progress(db_session, test_user.id, surah=112, ayah_from=3, ayah_to=3)

        assert streak.current_streak == 1
        assert streak.longest_streak == 1  # the earlier streak of 1 isn't beaten


class TestLeaderboard:
    def test_orders_by_requested_metric_descending(self, service, db_session):
        low_user = _make_user(db_session, "low-hasanat")
        high_user = _make_user(db_session, "high-hasanat")

        service.log_progress(db_session, low_user.id, surah=112, ayah_from=1, ayah_to=1)
        service.log_progress(db_session, high_user.id, surah=112, ayah_from=1, ayah_to=3)

        # A generous limit: this suite's shared test DB (see conftest.py)
        # accumulates UserStreak rows from every other test that logs
        # progress, so a small limit could push one of these two users out
        # of the window depending on test execution order.
        rows = service.get_leaderboard(db_session, metric="total_hasanat", limit=10000)
        usernames_in_order = [user_row.username for _, user_row in rows]

        assert usernames_in_order.index(high_user.username) < usernames_in_order.index(low_user.username)

    def test_rejects_unknown_metric(self, service, db_session):
        with pytest.raises(ValueError):
            service.get_leaderboard(db_session, metric="not_a_real_metric")
