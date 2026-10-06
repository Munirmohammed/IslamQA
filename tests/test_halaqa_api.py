"""
Halaqa API Tests
End-to-end through the real FastAPI TestClient. Fresh, uniquely-named
users per test -- same reasoning as the gamification/memorization API
tests (the shared persistent test DB).
"""

import uuid

import pytest


@pytest.fixture
def make_user(client):
    def _make(label: str):
        unique = uuid.uuid4().hex[:12]
        user_data = {
            "username": f"{label}-{unique}",
            "email": f"{label}-{unique}@example.com",
            "password": "testpassword123",
        }
        client.post("/api/v1/auth/register", json=user_data)
        response = client.post(
            "/api/v1/auth/login",
            data={"username": user_data["username"], "password": user_data["password"]},
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _make


class TestCreateAndJoinHalaqa:
    def test_requires_authentication(self, client):
        response = client.post("/api/v1/halaqa/create", json={"name": "My Circle"})
        assert response.status_code in (401, 403)

    def test_create_returns_join_code(self, client, make_user):
        teacher_headers = make_user("teacher")
        response = client.post("/api/v1/halaqa/create", json={"name": "My Circle"}, headers=teacher_headers)
        assert response.status_code == 200
        assert response.json()["join_code"]

    def test_student_can_join_with_code(self, client, make_user):
        teacher_headers = make_user("teacher")
        student_headers = make_user("student")

        created = client.post("/api/v1/halaqa/create", json={"name": "Circle"}, headers=teacher_headers)
        join_code = created.json()["join_code"]

        response = client.post("/api/v1/halaqa/join", json={"join_code": join_code}, headers=student_headers)
        assert response.status_code == 200

    def test_invalid_join_code_returns_404(self, client, make_user):
        student_headers = make_user("student")
        response = client.post(
            "/api/v1/halaqa/join", json={"join_code": "bogus-code"}, headers=student_headers
        )
        assert response.status_code == 404


class TestMyHalaqas:
    def test_lists_teaching_and_studying(self, client, make_user):
        teacher_headers = make_user("teacher")
        student_headers = make_user("student")

        created = client.post("/api/v1/halaqa/create", json={"name": "Circle"}, headers=teacher_headers)
        join_code = created.json()["join_code"]
        client.post("/api/v1/halaqa/join", json={"join_code": join_code}, headers=student_headers)

        teacher_view = client.get("/api/v1/halaqa/mine", headers=teacher_headers).json()
        student_view = client.get("/api/v1/halaqa/mine", headers=student_headers).json()

        assert len(teacher_view["teaching"]) == 1
        assert len(student_view["studying"]) == 1


class TestTeacherOnlyAccess:
    def test_non_teacher_gets_403_on_students_list(self, client, make_user):
        teacher_headers = make_user("teacher")
        student_headers = make_user("student")
        intruder_headers = make_user("intruder")

        created = client.post("/api/v1/halaqa/create", json={"name": "Circle"}, headers=teacher_headers)
        halaqa_id = created.json()["id"]
        join_code = created.json()["join_code"]
        client.post("/api/v1/halaqa/join", json={"join_code": join_code}, headers=student_headers)

        response = client.get(f"/api/v1/halaqa/{halaqa_id}/students", headers=intruder_headers)
        assert response.status_code == 403

    def test_teacher_sees_student_summary(self, client, make_user):
        teacher_headers = make_user("teacher")
        student_headers = make_user("student")

        created = client.post("/api/v1/halaqa/create", json={"name": "Circle"}, headers=teacher_headers)
        halaqa_id = created.json()["id"]
        join_code = created.json()["join_code"]
        client.post("/api/v1/halaqa/join", json={"join_code": join_code}, headers=student_headers)

        response = client.get(f"/api/v1/halaqa/{halaqa_id}/students", headers=teacher_headers)
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["session_count"] == 0

    def test_unknown_halaqa_returns_404(self, client, make_user):
        teacher_headers = make_user("teacher")
        response = client.get("/api/v1/halaqa/not-a-real-id/students", headers=teacher_headers)
        assert response.status_code == 404

    def test_student_not_in_halaqa_returns_404_for_sessions(self, client, make_user):
        teacher_headers = make_user("teacher")
        outsider_headers = make_user("outsider")

        created = client.post("/api/v1/halaqa/create", json={"name": "Circle"}, headers=teacher_headers)
        halaqa_id = created.json()["id"]

        # Get the outsider's user id via /gamification/me-equivalent isn't
        # available; use the halaqa/mine + a direct DB-free approach: just
        # assert 404 for an arbitrary non-member id, since no student with
        # that id is in this halaqa either way.
        response = client.get(
            f"/api/v1/halaqa/{halaqa_id}/students/not-a-real-student-id/sessions",
            headers=teacher_headers,
        )
        assert response.status_code == 404
