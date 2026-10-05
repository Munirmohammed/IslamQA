"""
Gamification API Tests
End-to-end checks through the real FastAPI TestClient (same pattern as
tests/test_api.py): register/login a real user, then hit the gamification
endpoints against the real Quran corpus data.

Deliberately does NOT reuse conftest's shared `auth_headers` fixture: that
fixture's "testuser" account is reused across the *entire* test session
(same persistent test.db -- see conftest.py), so its hasanat/verses totals
accumulate across every test file that touches it. Gamification state needs
a fresh, uniquely-named account per test to make exact-value assertions
meaningful instead of order-dependent.
"""

import uuid

import pytest


class FreshUser:
    def __init__(self, headers: dict, username: str):
        self.headers = headers
        self.username = username


@pytest.fixture
def fresh_user(client):
    """Register+login a brand-new, uniquely-named user so this test's
    streak/hasanat totals start from zero, independent of any other test."""
    unique = uuid.uuid4().hex[:12]
    user_data = {
        "username": f"gamify-{unique}",
        "email": f"gamify-{unique}@example.com",
        "password": "testpassword123",
    }
    client.post("/api/v1/auth/register", json=user_data)
    response = client.post(
        "/api/v1/auth/login",
        data={"username": user_data["username"], "password": user_data["password"]},
    )
    token = response.json()["access_token"]
    return FreshUser(headers={"Authorization": f"Bearer {token}"}, username=user_data["username"])


@pytest.fixture
def fresh_user_headers(fresh_user):
    return fresh_user.headers


class TestLogProgressEndpoint:
    def test_requires_authentication(self, client):
        response = client.post(
            "/api/v1/gamification/log-progress",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 1},
        )
        assert response.status_code in (401, 403)

    def test_logs_progress_for_authenticated_user(self, client, fresh_user_headers):
        response = client.post(
            "/api/v1/gamification/log-progress",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 3},
            headers=fresh_user_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_verses_read"] == 3
        assert data["total_hasanat"] > 0
        assert data["current_streak"] == 1

    def test_invalid_ayah_range_returns_400(self, client, fresh_user_headers):
        response = client.post(
            "/api/v1/gamification/log-progress",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 9999},
            headers=fresh_user_headers,
        )
        assert response.status_code == 400

    def test_second_log_same_day_accumulates_but_keeps_streak(self, client, fresh_user_headers):
        client.post(
            "/api/v1/gamification/log-progress",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 1},
            headers=fresh_user_headers,
        )
        response = client.post(
            "/api/v1/gamification/log-progress",
            json={"surah": 112, "ayah_from": 2, "ayah_to": 2},
            headers=fresh_user_headers,
        )
        data = response.json()
        assert data["total_verses_read"] == 2
        assert data["current_streak"] == 1


class TestMyStreakEndpoint:
    def test_requires_authentication(self, client):
        response = client.get("/api/v1/gamification/me")
        assert response.status_code in (401, 403)

    def test_returns_zeros_before_any_logging(self, client, fresh_user_headers):
        response = client.get("/api/v1/gamification/me", headers=fresh_user_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_hasanat"] == 0
        assert data["current_streak"] == 0

    def test_reflects_logged_progress(self, client, fresh_user_headers):
        client.post(
            "/api/v1/gamification/log-progress",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 1},
            headers=fresh_user_headers,
        )
        response = client.get("/api/v1/gamification/me", headers=fresh_user_headers)
        assert response.json()["total_verses_read"] == 1


class TestLeaderboardEndpoint:
    def test_accessible_without_authentication(self, client):
        response = client.get("/api/v1/gamification/leaderboard")
        assert response.status_code == 200
        assert "entries" in response.json()

    def test_rejects_unknown_metric(self, client):
        response = client.get("/api/v1/gamification/leaderboard?metric=bogus")
        assert response.status_code == 400

    def test_includes_user_after_logging_progress(self, client, fresh_user):
        client.post(
            "/api/v1/gamification/log-progress",
            json={"surah": 112, "ayah_from": 1, "ayah_to": 1},
            headers=fresh_user.headers,
        )
        leaderboard = client.get("/api/v1/gamification/leaderboard?limit=100")
        entries = leaderboard.json()["entries"]
        assert any(e["username"] == fresh_user.username for e in entries)
