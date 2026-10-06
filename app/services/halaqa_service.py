"""
Halaqa (Teacher/Student Circle) Service
Teacher-student relationships and the student-history views a teacher
dashboard needs. No fixed global "teacher" role on User: being a halaqa's
teacher_id makes you that halaqa's teacher, and nothing stops the same
account from also being a student elsewhere.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.database import Halaqa, HalaqaMembership, MistakeLog, RecitationSession, User


class HalaqaNotFoundError(Exception):
    pass


class InvalidJoinCodeError(Exception):
    pass


def create_halaqa(db: Session, teacher_id: str, name: str) -> Halaqa:
    halaqa = Halaqa(teacher_id=teacher_id, name=name)
    db.add(halaqa)
    db.commit()
    db.refresh(halaqa)
    return halaqa


def join_halaqa(db: Session, student_id: str, join_code: str) -> HalaqaMembership:
    halaqa = db.query(Halaqa).filter(Halaqa.join_code == join_code).first()
    if not halaqa:
        raise InvalidJoinCodeError(f"No halaqa found for join code {join_code!r}")

    existing = (
        db.query(HalaqaMembership)
        .filter(HalaqaMembership.halaqa_id == halaqa.id, HalaqaMembership.student_id == student_id)
        .first()
    )
    if existing:
        return existing

    membership = HalaqaMembership(halaqa_id=halaqa.id, student_id=student_id)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def get_my_halaqas(db: Session, user_id: str) -> Dict[str, List[Halaqa]]:
    teaching = db.query(Halaqa).filter(Halaqa.teacher_id == user_id).all()
    studying = (
        db.query(Halaqa)
        .join(HalaqaMembership, HalaqaMembership.halaqa_id == Halaqa.id)
        .filter(HalaqaMembership.student_id == user_id)
        .all()
    )
    return {"teaching": teaching, "studying": studying}


def get_halaqa_or_raise(db: Session, halaqa_id: str) -> Halaqa:
    halaqa = db.query(Halaqa).filter(Halaqa.id == halaqa_id).first()
    if not halaqa:
        raise HalaqaNotFoundError(f"Halaqa {halaqa_id} not found")
    return halaqa


def is_student_of(db: Session, halaqa_id: str, student_id: str) -> bool:
    return (
        db.query(HalaqaMembership)
        .filter(HalaqaMembership.halaqa_id == halaqa_id, HalaqaMembership.student_id == student_id)
        .first()
        is not None
    )


def get_student_summaries(db: Session, halaqa_id: str) -> List[Dict[str, Any]]:
    """Per-student summary stats for a teacher's roster view."""
    memberships = db.query(HalaqaMembership).filter(HalaqaMembership.halaqa_id == halaqa_id).all()

    summaries = []
    for membership in memberships:
        student = db.query(User).filter(User.id == membership.student_id).first()
        sessions = db.query(RecitationSession).filter(RecitationSession.user_id == membership.student_id).all()
        correct_count = sum(1 for s in sessions if s.is_correct)

        summaries.append({
            "student_id": membership.student_id,
            "username": student.username if student else "(deleted user)",
            "joined_at": membership.joined_at,
            "session_count": len(sessions),
            "correct_count": correct_count,
            "correct_rate": (correct_count / len(sessions)) if sessions else None,
        })
    return summaries


def get_student_sessions(db: Session, student_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """A student's recitation sessions, newest first, with their mistakes."""
    sessions = (
        db.query(RecitationSession)
        .filter(RecitationSession.user_id == student_id)
        .order_by(RecitationSession.created_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for session in sessions:
        mistakes = db.query(MistakeLog).filter(MistakeLog.session_id == session.id).all()
        results.append({
            "session_id": session.id,
            "surah_number": session.surah_number,
            "ayah_number": session.ayah_number,
            "transcript": session.transcript,
            "mistake_count": session.mistake_count,
            "is_correct": session.is_correct,
            "is_duplicate_submission": session.is_duplicate_submission,
            "created_at": session.created_at,
            "mistakes": [
                {"type": m.mistake_type, "expected": m.expected, "recited": m.recited, "position": m.position}
                for m in mistakes
            ],
        })
    return results


def record_recitation_session(
    db: Session,
    user_id: Optional[str],
    surah: int,
    ayah: int,
    transcript: str,
    mistakes: List[Dict[str, Any]],
    audio_hash: str,
) -> RecitationSession:
    """Persist a recitation-check result (called from the /recitation/check
    endpoint). Flags is_duplicate_submission when the same audio hash was
    already submitted by a *different* user/anonymous caller -- a narrow,
    honestly-labeled duplicate-file check, not real audio-liveness
    detection (see Phase 6 plan notes)."""
    # Known limitation: SQL's NULL != 'x' is UNKNOWN (not true), so an
    # authenticated user resubmitting an *anonymous* caller's exact audio
    # won't be caught here. Acceptable for a narrow, best-effort heuristic
    # that isn't real anti-cheat (see module docstring) -- the common case
    # this does catch is two different accounts submitting the same file.
    existing_submission = (
        db.query(RecitationSession)
        .filter(RecitationSession.audio_hash == audio_hash, RecitationSession.user_id != user_id)
        .first()
    )

    session = RecitationSession(
        user_id=user_id,
        surah_number=surah,
        ayah_number=ayah,
        transcript=transcript,
        mistake_count=len(mistakes),
        is_correct=len(mistakes) == 0,
        audio_hash=audio_hash,
        is_duplicate_submission=existing_submission is not None,
    )
    db.add(session)
    db.flush()  # assign session.id before creating MistakeLog rows that reference it

    for mistake in mistakes:
        db.add(MistakeLog(
            session_id=session.id,
            mistake_type=mistake["type"],
            expected=mistake["expected"],
            recited=mistake["recited"],
            position=mistake["position"],
        ))

    db.commit()
    db.refresh(session)
    return session
