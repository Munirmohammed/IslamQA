"""
Memorization API Tests
End-to-end checks through the real FastAPI TestClient. Uses a fresh,
uniquely-named user per test (same reasoning as test_gamification_api.py:
the shared "testuser" account from conftest's `auth_headers` persists
across the whole test session, so per-user state needs isolation).
"""

import uuid

import pytest


@pytest.fixture
def fresh_user_headers(client):
    unique = uuid.uuid4().hex[:12]
    user_data = {
        "username": f"hifz-{unique}",
        "email": f"hifz-{unique}@example.com",
        "password": "testpassword123",
    }
    client.post("/api/v1/auth/register", json=user_data)
    response = client.post(
        "/api/v1/auth/login",
        data={"username": user_data["username"], "password": user_data["password"]},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestAddToMemorization:
    def test_requires_authentication(self, client):
        response = client.post(
            "/api/v1/memorization/add", json={"surah": 112, "ayah_from": 1, "ayah_to": 3}
        )
        assert response.status_code in (401, 403)

    def test_creates_one_card_per_ayah(self, client, fresh_user_headers):
        response = client.post(
            "/api/v1/memorization/add",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 3},
            headers=fresh_user_headers,
        )
        assert response.status_code == 200
        cards = response.json()
        assert len(cards) == 3
        assert {c["ayah_number"] for c in cards} == {1, 2, 3}
        assert all(c["repetitions"] == 0 for c in cards)

    def test_invalid_ayah_returns_404(self, client, fresh_user_headers):
        response = client.post(
            "/api/v1/memorization/add",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 9999},
            headers=fresh_user_headers,
        )
        assert response.status_code == 404

    def test_adding_twice_is_idempotent(self, client, fresh_user_headers):
        client.post(
            "/api/v1/memorization/add",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 1},
            headers=fresh_user_headers,
        )
        response = client.post(
            "/api/v1/memorization/add",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 1},
            headers=fresh_user_headers,
        )
        assert len(response.json()) == 1


class TestDueCards:
    def test_newly_added_card_is_due_today(self, client, fresh_user_headers):
        client.post(
            "/api/v1/memorization/add",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 1},
            headers=fresh_user_headers,
        )
        response = client.get("/api/v1/memorization/due", headers=fresh_user_headers)
        assert response.status_code == 200
        due = response.json()
        assert any(c["surah_number"] == 112 and c["ayah_number"] == 1 for c in due)
        assert all("text_uthmani" in c and "translation_en" in c for c in due)


class TestReviewCard:
    def test_requires_card_to_exist(self, client, fresh_user_headers):
        response = client.post(
            "/api/v1/memorization/review",
            json={"surah": 112, "ayah": 1, "quality": 5},
            headers=fresh_user_headers,
        )
        assert response.status_code == 404

    def test_rejects_both_quality_and_mistake_count(self, client, fresh_user_headers):
        client.post(
            "/api/v1/memorization/add",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 1},
            headers=fresh_user_headers,
        )
        response = client.post(
            "/api/v1/memorization/review",
            json={"surah": 112, "ayah": 1, "quality": 5, "mistake_count": 0},
            headers=fresh_user_headers,
        )
        assert response.status_code == 422

    def test_direct_quality_grades_the_card(self, client, fresh_user_headers):
        client.post(
            "/api/v1/memorization/add",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 1},
            headers=fresh_user_headers,
        )
        response = client.post(
            "/api/v1/memorization/review",
            json={"surah": 112, "ayah": 1, "quality": 5},
            headers=fresh_user_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["repetitions"] == 1
        assert data["interval_days"] == 1

    def test_mistake_count_derives_quality(self, client, fresh_user_headers):
        """0 mistakes -> quality 5 -> same SM-2 outcome as a direct
        quality=5 review (interval=1, repetitions=1)."""
        client.post(
            "/api/v1/memorization/add",
            json={"surah": 112, "ayah_from": 2, "ayah_to": 2},
            headers=fresh_user_headers,
        )
        response = client.post(
            "/api/v1/memorization/review",
            json={"surah": 112, "ayah": 2, "mistake_count": 0},
            headers=fresh_user_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["repetitions"] == 1
        assert data["interval_days"] == 1

    def test_many_mistakes_resets_progress(self, client, fresh_user_headers):
        client.post(
            "/api/v1/memorization/add",
            json={"surah": 112, "ayah_from": 3, "ayah_to": 3},
            headers=fresh_user_headers,
        )
        client.post(
            "/api/v1/memorization/review",
            json={"surah": 112, "ayah": 3, "quality": 5},
            headers=fresh_user_headers,
        )
        response = client.post(
            "/api/v1/memorization/review",
            json={"surah": 112, "ayah": 3, "mistake_count": 10},
            headers=fresh_user_headers,
        )
        data = response.json()
        assert data["repetitions"] == 0
        assert data["interval_days"] == 1


class TestSimilarAyahs:
    def test_finds_known_repeated_phrase(self, client):
        """Surah Ar-Rahman's refrain ('فبأي آلاء ربكما تكذبان') repeats 31
        times -- a real mutashabihat case any of those ayahs should surface
        several of the others for."""
        response = client.get("/api/v1/memorization/similar/55/13?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["similar"]) > 0
        # Should not include the queried ayah itself
        assert not any(s["surah_number"] == 55 and s["ayah_number"] == 13 for s in data["similar"])

    def test_unknown_ayah_returns_404(self, client):
        response = client.get("/api/v1/memorization/similar/112/9999")
        assert response.status_code == 404
