"""
Voice Search Service Tests
Covers the BM25 + char n-gram fuzzy + RRF fusion wiring over a tiny ayah
corpus, without loading the real SentenceTransformer/cross-encoder models
(slow, network-dependent downloads) -- `_dense_search` is stubbed out the
same way test_ml_service.py stubs FAISS, and reranking is disabled via
settings, isolating the part of VoiceSearchService that doesn't need a
live model.
"""

import pytest

from app.core.config import settings
from app.services.voice_search_service import VoiceSearchService

FIXTURE_AYAHS = [
    {
        "key": "112:1", "surah_number": 112, "ayah_number": 1,
        "surah_name_ar": "الإخلاص", "surah_name_en": "Al-Ikhlas",
        "surah_name_translation_en": "Sincerity", "revelation_type": "Meccan",
        "global_ayah_number": 6222, "juz": 30, "page": 604,
        "text_uthmani": "قُلْ هُوَ اللَّهُ أَحَدٌ", "text_simple": "قل هو الله احد",
        "translation_en": "Say, 'He is Allah, [who is] One,'",
    },
    {
        "key": "112:2", "surah_number": 112, "ayah_number": 2,
        "surah_name_ar": "الإخلاص", "surah_name_en": "Al-Ikhlas",
        "surah_name_translation_en": "Sincerity", "revelation_type": "Meccan",
        "global_ayah_number": 6223, "juz": 30, "page": 604,
        "text_uthmani": "اللَّهُ الصَّمَدُ", "text_simple": "الله الصمد",
        "translation_en": "Allah, the Eternal Refuge.",
    },
    {
        "key": "18:10", "surah_number": 18, "ayah_number": 10,
        "surah_name_ar": "الكهف", "surah_name_en": "Al-Kahf",
        "surah_name_translation_en": "The Cave", "revelation_type": "Meccan",
        "global_ayah_number": 2145, "juz": 15, "page": 294,
        "text_uthmani": "إِذْ أَوَى الْفِتْيَةُ إِلَى الْكَهْفِ",
        "text_simple": "اذ اوى الفتيه الى الكهف",
        "translation_en": "When the youths retreated to the cave...",
    },
]


@pytest.fixture
def voice_search_service(monkeypatch, tmp_path):
    """A VoiceSearchService with its BM25/fuzzy indexes built over the tiny
    fixture corpus above, dense search stubbed to return nothing (isolating
    the sparse+fuzzy+fusion path), and reranking disabled (no cross-encoder
    model load)."""
    monkeypatch.setattr(settings, "ENABLE_RERANKING", False)

    service = VoiceSearchService()
    # Redirect BM25 persistence to a throwaway path -- _build_bm25_index
    # writes to disk, and the real data/quran/ index must not be clobbered
    # with this tiny fixture corpus.
    service.bm25_index.index_path = str(tmp_path / "bm25.pkl")
    service.bm25_index.ids_path = str(tmp_path / "bm25_ids.pkl")
    service.ayahs_by_key = {a["key"]: a for a in FIXTURE_AYAHS}
    service._build_bm25_index(FIXTURE_AYAHS, force_rebuild=True)
    service._build_char_ngram_index(FIXTURE_AYAHS)
    service._dense_search = lambda query, top_k: []
    service.is_initialized = True
    return service


class TestVoiceSearchExactAndFragmentMatches:
    @pytest.mark.asyncio
    async def test_exact_ayah_text_ranks_first(self, voice_search_service):
        result = await voice_search_service.search("قل هو الله احد", top_k=3)
        assert result["results"][0]["key"] == "112:1"

    @pytest.mark.asyncio
    async def test_mid_ayah_fragment_ranks_first(self, voice_search_service):
        """A fragment recited from partway through an ayah (not just its
        opening words) should still surface the correct ayah -- the core
        'Tasmeea' use case."""
        result = await voice_search_service.search("الفتيه الى الكهف", top_k=3)
        assert result["results"][0]["key"] == "18:10"

    @pytest.mark.asyncio
    async def test_unmatched_query_returns_no_crash(self, voice_search_service):
        result = await voice_search_service.search("zzz not arabic at all zzz", top_k=3)
        assert result["query"] == "zzz not arabic at all zzz"
        assert isinstance(result["results"], list)


class TestVoiceSearchFuzzyFallback:
    @pytest.mark.asyncio
    async def test_corrupted_keyword_still_found_via_char_ngram_fallback(self, voice_search_service):
        """Same OCR/noise-tolerance property as test_fuzzy_match.py's char
        n-gram fallback, applied to a Quran ayah: a single-letter substitution
        (ص -> س in 'الصمد') zeroes out BM25's token-level match, but the
        char n-gram fallback should still recover it."""
        bm25_hits = voice_search_service.bm25_index.search("السمد", "ar", top_k=5)
        assert dict(bm25_hits).get("112:2", 0.0) == 0.0, (
            "expected BM25 to have zero signal for this corrupted keyword "
            "-- if it doesn't, this is no longer a useful fuzzy-fallback test"
        )

        result = await voice_search_service.search("السمد", top_k=3)
        assert result["results"][0]["key"] == "112:2"
