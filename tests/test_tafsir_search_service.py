"""
Tafsir Search Service Tests
Mirrors test_voice_search_service.py's approach exactly: a tiny fixture
corpus, BM25/char-ngram indexes built directly (no network/model loading),
dense search stubbed out, reranking disabled.
"""

import pytest

from app.core.config import settings
from app.services.tafsir_search_service import TafsirSearchService, _unique_blocks

FIXTURE_BLOCKS = [
    {
        "surah_number": 112, "ayah_from": 1, "ayah_to": 4,
        "text_html": "<p>x</p>",
        "text_plain": "This surah was revealed in Makkah and explains the oneness of Allah, "
                       "that He begets not nor was He begotten, and there is none comparable to Him.",
    },
    {
        "surah_number": 2, "ayah_from": 255, "ayah_to": 255,
        "text_html": "<p>x</p>",
        "text_plain": "This is Ayat al-Kursi, the Throne Verse, describing Allah's complete "
                       "knowledge and dominion over the heavens and the earth.",
    },
    {
        "surah_number": 18, "ayah_from": 9, "ayah_to": 12,
        "text_html": "<p>x</p>",
        "text_plain": "This passage discusses the People of the Cave, young believers who fled "
                       "persecution and were granted a long sleep as a sign from Allah.",
    },
]


class TestUniqueBlocks:
    def test_deduplicates_shared_block_across_ayah_keys(self):
        by_key = {
            "112:1": {"surah_number": 112, "ayah_from": 1, "ayah_to": 4, "text_plain": "x"},
            "112:2": {"surah_number": 112, "ayah_from": 1, "ayah_to": 4, "text_plain": "x"},
            "2:255": {"surah_number": 2, "ayah_from": 255, "ayah_to": 255, "text_plain": "y"},
        }
        unique = _unique_blocks(by_key)
        assert len(unique) == 2
        assert "112:1-4" in unique
        assert "2:255-255" in unique


@pytest.fixture
def tafsir_search_service(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ENABLE_RERANKING", False)

    service = TafsirSearchService()
    service.bm25_index.index_path = str(tmp_path / "bm25.pkl")
    service.bm25_index.ids_path = str(tmp_path / "bm25_ids.pkl")

    service.blocks_by_key = {
        f"{b['surah_number']}:{b['ayah_from']}-{b['ayah_to']}": b for b in FIXTURE_BLOCKS
    }
    service.block_keys = list(service.blocks_by_key.keys())
    blocks = list(service.blocks_by_key.values())

    service._build_bm25_index(blocks, force_rebuild=True)
    service._build_char_ngram_index(blocks)
    service._dense_search = lambda query, top_k: []
    service.is_initialized = True
    return service


class TestTafsirSearch:
    @pytest.mark.asyncio
    async def test_finds_ayat_al_kursi_by_topic(self, tafsir_search_service):
        result = await tafsir_search_service.search("Throne Verse dominion heavens earth", top_k=3)
        assert result["results"][0]["surah_number"] == 2

    @pytest.mark.asyncio
    async def test_finds_cave_passage_by_topic(self, tafsir_search_service):
        result = await tafsir_search_service.search("People of the Cave young believers", top_k=3)
        assert result["results"][0]["surah_number"] == 18

    @pytest.mark.asyncio
    async def test_unmatched_query_does_not_crash(self, tafsir_search_service):
        result = await tafsir_search_service.search("completely unrelated nonsense topic", top_k=3)
        assert isinstance(result["results"], list)
