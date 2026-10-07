"""
Quran Content API Tests
Plain read/browse access over the real Quran corpus (Phase 1) -- no auth,
no network dependency beyond the already-cached corpus every other test
in this suite already warms via the app's real lifespan.
"""

from app.services.quran_corpus_service import QuranCorpusService


class TestListSurahs:
    def test_returns_all_114_surahs(self, client):
        response = client.get("/api/v1/quran/surahs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 114

    def test_al_fatiha_has_seven_ayahs(self, client):
        response = client.get("/api/v1/quran/surahs")
        al_fatiha = next(s for s in response.json() if s["surah_number"] == 1)
        assert al_fatiha["ayah_count"] == 7
        assert al_fatiha["surah_name_en"] == "Al-Faatiha"

    def test_sorted_by_surah_number(self, client):
        response = client.get("/api/v1/quran/surahs")
        numbers = [s["surah_number"] for s in response.json()]
        assert numbers == sorted(numbers)


class TestGetSurah:
    def test_al_ikhlas_returns_four_ayahs_in_order(self, client):
        """text_simple is compared against the real corpus directly rather
        than a hand-typed literal: Arabic combining marks/hamza spelling
        are easy to mistype by hand and this isn't what the test is
        actually meant to verify (see test_quran_corpus_service.py for
        that), just that the API serves the real corpus's own data."""
        response = client.get("/api/v1/quran/112")
        assert response.status_code == 200
        data = response.json()
        assert data["surah_name_en"] == "Al-Ikhlaas"
        assert [a["ayah_number"] for a in data["ayahs"]] == [1, 2, 3, 4]

        expected = QuranCorpusService().load_or_fetch()
        expected_112_1 = next(a for a in expected if a["key"] == "112:1")
        assert data["ayahs"][0]["text_simple"] == expected_112_1["text_simple"]

    def test_unknown_surah_returns_404(self, client):
        response = client.get("/api/v1/quran/9999")
        assert response.status_code == 404

    def test_basmalah_present_for_ordinary_surah_ayah_one(self, client):
        """Regression check for the Phase 1 Basmalah-embedding fix: surah
        112's ayah 1 should carry the Basmalah in its own field, not
        embedded in text_simple."""
        response = client.get("/api/v1/quran/112")
        first_ayah = response.json()["ayahs"][0]
        assert first_ayah["basmalah"] is not None
        assert "بسم" not in first_ayah["text_simple"]
