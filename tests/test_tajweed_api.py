"""
Tajweed API Tests
End-to-end through the real FastAPI TestClient and the real (startup-
warmed) tajweed cache -- public endpoints, no auth needed.
"""


class TestTajweedRulesLegend:
    def test_returns_all_known_rules(self, client):
        response = client.get("/api/v1/tajweed/rules")
        assert response.status_code == 200
        codes = {r["rule"] for r in response.json()}
        assert len(codes) == 17
        assert "qalaqah" in codes
        assert "ham_wasl" in codes
        assert "idgham_mutaqaribayn" in codes


class TestGetAyahTajweed:
    def test_returns_ham_wasl_and_qalaqah_for_112_1(self, client):
        response = client.get("/api/v1/tajweed/112/1")
        assert response.status_code == 200
        data = response.json()
        # Exact plain-text equality against a hand-typed literal is covered
        # (against ground truth derived from the real markup, not a manual
        # retype) in test_tajweed_service.py -- here just confirm the rule
        # spans the endpoint wiring returns are correct.
        assert data["plain_text"].startswith("قُلْ")
        rules_by_class = {r["rule"]: r["text"] for r in data["rules"]}
        assert rules_by_class == {"ham_wasl": "ٱ", "qalaqah": "د"}

    def test_rule_includes_human_readable_name(self, client):
        response = client.get("/api/v1/tajweed/112/1")
        qalaqah_rule = next(r for r in response.json()["rules"] if r["rule"] == "qalaqah")
        assert qalaqah_rule["name"] == "Qalqalah"

    def test_unknown_ayah_returns_404(self, client):
        response = client.get("/api/v1/tajweed/112/9999")
        assert response.status_code == 404
