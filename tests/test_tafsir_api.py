"""
Tafsir API Tests
End-to-end through the real FastAPI TestClient and the real (startup-
warmed) tafsir corpus/search index -- public endpoints, no auth needed.
"""


class TestGetAyahTafsir:
    def test_112_1_and_112_2_return_the_same_shared_block(self, client):
        response_1 = client.get("/api/v1/tafsir/112/1")
        response_2 = client.get("/api/v1/tafsir/112/2")

        assert response_1.status_code == 200
        assert response_2.status_code == 200

        data_1, data_2 = response_1.json(), response_2.json()
        assert data_1["ayah_from"] == 1
        assert data_1["ayah_to"] == 4
        assert data_2["ayah_from"] == 1
        assert data_2["ayah_to"] == 4
        # 112:2 must NOT come back empty -- it shares 112:1's commentary.
        assert data_2["text_plain"] == data_1["text_plain"]
        assert len(data_2["text_plain"]) > 100

    def test_unknown_ayah_returns_404(self, client):
        response = client.get("/api/v1/tafsir/112/9999")
        assert response.status_code == 404


class TestTafsirSearch:
    def test_search_finds_ayat_al_kursi_by_name(self, client):
        """Verified manually against the real corpus: the named term
        ranks the right passage #1. A generic paraphrase (e.g. "dominion
        over heavens and earth") does *not* reliably do this -- that theme
        recurs across dozens of unrelated passages in a corpus this size,
        so a vague paraphrase is a genuinely harder/more ambiguous query,
        not a retrieval bug."""
        response = client.get("/api/v1/tafsir/search?q=Ayat al-Kursi")
        assert response.status_code == 200
        data = response.json()
        assert data["total_results"] > 0
        assert data["results"][0]["surah_number"] == 2
        assert data["results"][0]["ayah_from"] == 255

    def test_search_requires_minimum_query_length(self, client):
        response = client.get("/api/v1/tafsir/search?q=a")
        assert response.status_code == 422
