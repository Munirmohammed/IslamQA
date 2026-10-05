"""
Quran Corpus Service Tests
Covers the edition-merging logic and the load-or-fetch disk cache, without
hitting the live alquran.cloud API (that would make the suite slow, flaky,
and network-dependent -- the merge logic itself is pure and fully testable
against small hand-built edition payloads shaped like the real API response).
"""

import json
import os

import pytest

from app.services.quran_corpus_service import QuranCorpusService


def _edition_payload(ayahs_by_surah):
    """Build a minimal {edition_key: [surah...]} structure matching the
    shape of alquran.cloud's /v1/quran/{edition} response's "surahs" list."""
    return [
        {
            "number": surah_number,
            "name": f"arabic-name-{surah_number}",
            "englishName": f"English {surah_number}",
            "englishNameTranslation": f"Translation {surah_number}",
            "revelationType": "Meccan",
            "ayahs": [
                {"number": global_num, "numberInSurah": ayah_number, "juz": 1, "page": 1, "text": text}
                for ayah_number, global_num, text in ayahs
            ],
        }
        for surah_number, ayahs in ayahs_by_surah.items()
    ]


class TestMergeEditions:
    def test_merges_three_editions_into_flat_keyed_ayah_list(self):
        service = QuranCorpusService()

        uthmani = _edition_payload({1: [(1, 1, "uthmani-text-1"), (2, 2, "uthmani-text-2")]})
        simple = _edition_payload({1: [(1, 1, "simple-text-1"), (2, 2, "simple-text-2")]})
        translation = _edition_payload({1: [(1, 1, "translation-1"), (2, 2, "translation-2")]})

        merged = service._merge_editions({
            "uthmani": uthmani,
            "simple": simple,
            "translation_en": translation,
        })

        assert len(merged) == 2
        assert merged[0]["key"] == "1:1"
        assert merged[0]["text_uthmani"] == "uthmani-text-1"
        assert merged[0]["text_simple"] == "simple-text-1"
        assert merged[0]["translation_en"] == "translation-1"
        assert merged[1]["key"] == "1:2"

    def test_preserves_surah_and_location_metadata(self):
        service = QuranCorpusService()
        uthmani = _edition_payload({2: [(255, 282, "ayat-al-kursi")]})
        simple = _edition_payload({2: [(255, 282, "ayat-al-kursi-simple")]})
        translation = _edition_payload({2: [(255, 282, "throne-verse")]})

        merged = service._merge_editions({
            "uthmani": uthmani, "simple": simple, "translation_en": translation,
        })

        ayah = merged[0]
        assert ayah["surah_number"] == 2
        assert ayah["ayah_number"] == 255
        assert ayah["global_ayah_number"] == 282
        assert ayah["key"] == "2:255"


class TestLoadOrFetchCache:
    def test_loads_from_disk_cache_without_network_call(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "quran_corpus.json"
        fixture_ayahs = [
            {"surah_number": 1, "ayah_number": 1, "key": "1:1", "text_simple": "x"},
        ]
        cache_path.write_text(json.dumps(fixture_ayahs), encoding="utf-8")

        def fail_if_called(*args, **kwargs):
            raise AssertionError("should not hit the network when a valid cache exists")

        monkeypatch.setattr("app.services.quran_corpus_service.requests.get", fail_if_called)

        service = QuranCorpusService(corpus_path=str(cache_path))
        ayahs = service.load_or_fetch()

        assert ayahs == fixture_ayahs
        assert service.get_ayah(1, 1) == fixture_ayahs[0]

    def test_corrupt_cache_falls_back_to_live_fetch_and_rewrites_cache(self, tmp_path, monkeypatch):
        """A cache file that fails to parse should fall through to the
        network-fetch branch (exercising the real merge + re-cache logic,
        not just a mocked-out shortcut), using a faked `requests.get`."""
        cache_path = tmp_path / "quran_corpus.json"
        cache_path.write_text("not valid json", encoding="utf-8")

        uthmani = _edition_payload({1: [(1, 1, "uthmani-text-1")]})
        simple = _edition_payload({1: [(1, 1, "simple-text-1")]})
        translation = _edition_payload({1: [(1, 1, "translation-1")]})
        payload_by_edition_id = {
            "quran-uthmani": uthmani,
            "quran-simple-clean": simple,
            "en.sahih": translation,
        }

        class FakeResponse:
            def __init__(self, surahs):
                self._surahs = surahs

            def raise_for_status(self):
                pass

            def json(self):
                return {"data": {"surahs": self._surahs}}

        def fake_get(url, timeout=30):
            edition_id = url.rsplit("/", 1)[-1]
            return FakeResponse(payload_by_edition_id[edition_id])

        monkeypatch.setattr("app.services.quran_corpus_service.requests.get", fake_get)

        service = QuranCorpusService(corpus_path=str(cache_path))
        ayahs = service.load_or_fetch()

        assert ayahs == [{
            "surah_number": 1,
            "surah_name_ar": "arabic-name-1",
            "surah_name_en": "English 1",
            "surah_name_translation_en": "Translation 1",
            "revelation_type": "Meccan",
            "ayah_number": 1,
            "global_ayah_number": 1,
            "juz": 1,
            "page": 1,
            "text_uthmani": "uthmani-text-1",
            "text_simple": "simple-text-1",
            "translation_en": "translation-1",
            "key": "1:1",
        }]
        # The corrupt cache file should have been overwritten with valid JSON.
        assert json.loads(cache_path.read_text(encoding="utf-8")) == ayahs
