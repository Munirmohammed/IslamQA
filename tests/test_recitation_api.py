"""
Recitation Check API Tests
End-to-end through the real FastAPI TestClient and the real ASR model --
the first endpoint-level test for /recitation/check (previously only
recitation_diff_service and recitation_asr_service had direct tests).
Primarily a Phase 6 regression test: confirms the persistence side effect
(RecitationSession + MistakeLog rows) added in Phase 6 works, while the
response shape stays exactly Phase 2's original contract.
"""

import os

import pytest

from app.core.database import MistakeLog, RecitationSession

FIXTURE_AUDIO_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "audio", "112_001_alafasy.mp3")


def _upload_fixture_audio(client, db_session=None, **form_fields):
    with open(FIXTURE_AUDIO_PATH, "rb") as f:
        return client.post(
            "/api/v1/recitation/check",
            files={"audio": ("112_001_alafasy.mp3", f, "audio/mpeg")},
            data=form_fields,
        )


@pytest.mark.slow
@pytest.mark.integration
class TestRecitationCheckPersistence:
    def test_response_shape_matches_phase_2_contract(self, client):
        response = _upload_fixture_audio(client, surah=112, ayah=1)
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {
            "transcript", "surah_number", "surah_name_en", "ayah_number",
            "key", "text_uthmani", "translation_en", "mistakes", "is_correct",
        }
        assert data["is_correct"] is True
        assert data["mistakes"] == []

    def test_persists_recitation_session_and_no_mistakes(self, client, db_session):
        response = _upload_fixture_audio(client, surah=112, ayah=1)
        assert response.status_code == 200

        session = (
            db_session.query(RecitationSession)
            .filter(RecitationSession.surah_number == 112, RecitationSession.ayah_number == 1)
            .order_by(RecitationSession.created_at.desc())
            .first()
        )
        assert session is not None
        assert session.is_correct is True
        assert session.mistake_count == 0
        assert session.transcript == response.json()["transcript"]

        mistake_logs = db_session.query(MistakeLog).filter(MistakeLog.session_id == session.id).all()
        assert mistake_logs == []

    def test_anonymous_submission_has_null_user_id(self, client, db_session):
        _upload_fixture_audio(client, surah=112, ayah=1)
        session = (
            db_session.query(RecitationSession)
            .filter(RecitationSession.surah_number == 112, RecitationSession.ayah_number == 1)
            .order_by(RecitationSession.created_at.desc())
            .first()
        )
        assert session.user_id is None

    def test_duplicate_audio_from_different_users_is_flagged(self, client, db_session):
        """The same audio bytes submitted by two different authenticated
        users should flag the second submission. (Per halaqa_service's
        documented limitation, SQL's `user_id != NULL` is UNKNOWN, so this
        specifically needs two *authenticated* users -- an authenticated
        resubmission of an anonymous caller's audio isn't caught.)"""
        import uuid
        user_a = {
            "username": f"dup-a-{uuid.uuid4().hex[:8]}",
            "email": f"dup-a-{uuid.uuid4().hex[:8]}@example.com",
            "password": "testpassword123",
        }
        user_b = {
            "username": f"dup-b-{uuid.uuid4().hex[:8]}",
            "email": f"dup-b-{uuid.uuid4().hex[:8]}@example.com",
            "password": "testpassword123",
        }
        for user_data in (user_a, user_b):
            client.post("/api/v1/auth/register", json=user_data)

        def _headers_for(user_data):
            login = client.post(
                "/api/v1/auth/login",
                data={"username": user_data["username"], "password": user_data["password"]},
            )
            return {"Authorization": f"Bearer {login.json()['access_token']}"}

        headers_a = _headers_for(user_a)
        headers_b = _headers_for(user_b)

        with open(FIXTURE_AUDIO_PATH, "rb") as f:
            client.post(
                "/api/v1/recitation/check",
                files={"audio": ("a.mp3", f, "audio/mpeg")},
                data={"surah": 112, "ayah": 1},
                headers=headers_a,
            )
        with open(FIXTURE_AUDIO_PATH, "rb") as f:
            client.post(
                "/api/v1/recitation/check",
                files={"audio": ("b.mp3", f, "audio/mpeg")},
                data={"surah": 112, "ayah": 1},
                headers=headers_b,
            )

        sessions = (
            db_session.query(RecitationSession)
            .filter(RecitationSession.surah_number == 112, RecitationSession.ayah_number == 1)
            .order_by(RecitationSession.created_at.desc())
            .limit(2)
            .all()
        )
        assert sessions[0].is_duplicate_submission is True
