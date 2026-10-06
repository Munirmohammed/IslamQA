"""
Halaqa Service Tests
Covers create/join/idempotent-rejoin, teacher-vs-student listing, and
student session retrieval, using the shared in-memory db_session fixture
(unique usernames per test -- the shared persistent test DB, same reason
as the gamification/SRS test suites).
"""

import uuid

import pytest

from app.core.database import User
from app.services import halaqa_service
from app.services.halaqa_service import HalaqaNotFoundError, InvalidJoinCodeError


def _make_user(db_session, label: str) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(username=f"{label}-{unique}", email=f"{label}-{unique}@example.com", hashed_password="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def teacher(db_session):
    return _make_user(db_session, "teacher")


@pytest.fixture
def student(db_session):
    return _make_user(db_session, "student")


class TestCreateAndJoin:
    def test_create_assigns_teacher_and_join_code(self, db_session, teacher):
        halaqa = halaqa_service.create_halaqa(db_session, teacher.id, "Tajweed Circle")
        assert halaqa.teacher_id == teacher.id
        assert halaqa.join_code

    def test_join_with_valid_code_creates_membership(self, db_session, teacher, student):
        halaqa = halaqa_service.create_halaqa(db_session, teacher.id, "Circle")
        membership = halaqa_service.join_halaqa(db_session, student.id, halaqa.join_code)
        assert membership.halaqa_id == halaqa.id
        assert membership.student_id == student.id

    def test_join_with_invalid_code_raises(self, db_session, student):
        with pytest.raises(InvalidJoinCodeError):
            halaqa_service.join_halaqa(db_session, student.id, "not-a-real-code")

    def test_rejoining_is_idempotent(self, db_session, teacher, student):
        halaqa = halaqa_service.create_halaqa(db_session, teacher.id, "Circle")
        first = halaqa_service.join_halaqa(db_session, student.id, halaqa.join_code)
        second = halaqa_service.join_halaqa(db_session, student.id, halaqa.join_code)
        assert first.id == second.id


class TestMyHalaqas:
    def test_lists_teaching_and_studying_separately(self, db_session, teacher, student):
        taught = halaqa_service.create_halaqa(db_session, teacher.id, "Taught Circle")
        other = halaqa_service.create_halaqa(db_session, student.id, "Other Teacher's Circle")
        halaqa_service.join_halaqa(db_session, teacher.id, other.join_code)

        mine = halaqa_service.get_my_halaqas(db_session, teacher.id)
        teaching_ids = {h.id for h in mine["teaching"]}
        studying_ids = {h.id for h in mine["studying"]}

        assert teaching_ids == {taught.id}
        assert studying_ids == {other.id}


class TestGetHalaqaOrRaise:
    def test_unknown_halaqa_raises(self, db_session):
        with pytest.raises(HalaqaNotFoundError):
            halaqa_service.get_halaqa_or_raise(db_session, "not-a-real-id")


class TestStudentSummariesAndSessions:
    def test_student_with_no_sessions_has_null_correct_rate(self, db_session, teacher, student):
        halaqa = halaqa_service.create_halaqa(db_session, teacher.id, "Circle")
        halaqa_service.join_halaqa(db_session, student.id, halaqa.join_code)

        summaries = halaqa_service.get_student_summaries(db_session, halaqa.id)
        assert len(summaries) == 1
        assert summaries[0]["student_id"] == student.id
        assert summaries[0]["session_count"] == 0
        assert summaries[0]["correct_rate"] is None

    def test_recorded_session_appears_in_student_sessions(self, db_session, student):
        halaqa_service.record_recitation_session(
            db_session, user_id=student.id, surah=112, ayah=1,
            transcript="قل هو الله احد",
            mistakes=[{"type": "incorrect", "expected": "احد", "recited": "واحد", "position": 3}],
            audio_hash="deadbeef",
        )

        sessions = halaqa_service.get_student_sessions(db_session, student.id, limit=10)
        assert len(sessions) == 1
        assert sessions[0]["mistake_count"] == 1
        assert sessions[0]["is_correct"] is False
        assert sessions[0]["mistakes"][0]["type"] == "incorrect"

    def test_duplicate_audio_hash_from_different_user_is_flagged(self, db_session, teacher, student):
        halaqa_service.record_recitation_session(
            db_session, user_id=teacher.id, surah=112, ayah=1,
            transcript="قل هو الله احد", mistakes=[], audio_hash="sharedhash",
        )
        second = halaqa_service.record_recitation_session(
            db_session, user_id=student.id, surah=112, ayah=1,
            transcript="قل هو الله احد", mistakes=[], audio_hash="sharedhash",
        )
        assert second.is_duplicate_submission is True

    def test_same_user_resubmitting_is_not_flagged(self, db_session, student):
        halaqa_service.record_recitation_session(
            db_session, user_id=student.id, surah=112, ayah=1,
            transcript="قل هو الله احد", mistakes=[], audio_hash="myownhash",
        )
        second = halaqa_service.record_recitation_session(
            db_session, user_id=student.id, surah=112, ayah=1,
            transcript="قل هو الله احد", mistakes=[], audio_hash="myownhash",
        )
        assert second.is_duplicate_submission is False
