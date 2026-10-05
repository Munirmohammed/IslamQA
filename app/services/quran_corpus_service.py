"""
Quran Corpus Service
Loads the canonical Quran ayah corpus (text + translation + metadata) from
the Tanzil-sourced alquran.cloud API, caching the merged result to disk so
runtime startup doesn't depend on a live network call every time -- the same
load-or-build persistence pattern as BM25Index / VectorEmbeddings.build_faiss_index.

Ayahs aren't modeled in the SQL database (unlike Question/Answer): the
corpus is fixed, externally verifiable reference data, not user-submitted
content, so it's kept as a standalone cached dataset instead.
"""

import json
import os
from typing import Any, Dict, List, Optional

import requests
import structlog

logger = structlog.get_logger()

CORPUS_PATH = "data/quran/quran_corpus.json"
BASE_URL = "https://api.alquran.cloud/v1/quran/{edition}"

# Tanzil-sourced editions served via alquran.cloud: Uthmani script (canonical
# display), simple-clean (diacritic-free -- best as the search/match text
# against noisy recitation transcripts), and the Saheeh International
# English translation.
EDITIONS = {
    "uthmani": "quran-uthmani",
    "simple": "quran-simple-clean",
    "translation_en": "en.sahih",
}
EXPECTED_AYAH_COUNT = 6236

# alquran.cloud's text editions embed the Basmalah into ayah 1's text for
# every surah except Al-Fatiha (where the Basmalah *is* ayah 1) and
# At-Tawbah (which has none) -- this matches traditional mushaf printing,
# but it means exact-text matching (recitation diffing, and to a lesser
# extent voice search) would wrongly flag a correct recitation of just the
# ayah itself as "missing" the Basmalah. Stripped out here into its own
# field so text_uthmani/text_simple hold only the ayah's own recitable
# content, with the Basmalah still available for display.
#
# Detection is done on the diacritic-free `simple` text (an exact literal
# match there is reliable); the same *word count* is then stripped from the
# Uthmani text rather than literal-matching a hand-typed, diacritic-heavy
# Uthmani Basmalah string (fragile -- one wrong diacritic byte and the match
# silently fails). Word boundaries line up between the two editions since
# Uthmani is the same text as simple, just with diacritics attached to
# existing letters, not inserted as extra tokens.
BASMALAH_SIMPLE = "بسم الله الرحمن الرحيم"
BASMALAH_WORD_COUNT = len(BASMALAH_SIMPLE.split())
SURAHS_WITHOUT_LEADING_BASMALAH = {1, 9}


class QuranCorpusService:
    """Loads and serves the full Quran ayah corpus."""

    def __init__(self, corpus_path: str = CORPUS_PATH):
        self.corpus_path = corpus_path
        self.ayahs: List[Dict[str, Any]] = []
        self._by_key: Dict[str, Dict[str, Any]] = {}

    def load_or_fetch(self, force_refetch: bool = False) -> List[Dict[str, Any]]:
        """Load the cached corpus from disk, or fetch and cache it if absent."""
        if not force_refetch and os.path.exists(self.corpus_path):
            try:
                with open(self.corpus_path, encoding="utf-8") as f:
                    self.ayahs = json.load(f)
                self._index_by_key()
                logger.info(f"Loaded cached Quran corpus with {len(self.ayahs)} ayahs")
                return self.ayahs
            except Exception:
                logger.warning("Failed to load cached Quran corpus, refetching...")

        logger.info("Fetching Quran corpus from alquran.cloud...")
        editions: Dict[str, List[Dict[str, Any]]] = {}
        for key, edition_id in EDITIONS.items():
            response = requests.get(BASE_URL.format(edition=edition_id), timeout=30)
            response.raise_for_status()
            editions[key] = response.json()["data"]["surahs"]

        self.ayahs = self._merge_editions(editions)

        if len(self.ayahs) != EXPECTED_AYAH_COUNT:
            logger.warning(
                f"Fetched {len(self.ayahs)} ayahs, expected {EXPECTED_AYAH_COUNT}"
            )

        os.makedirs(os.path.dirname(self.corpus_path), exist_ok=True)
        with open(self.corpus_path, "w", encoding="utf-8") as f:
            json.dump(self.ayahs, f, ensure_ascii=False)

        self._index_by_key()
        logger.info(f"Fetched and cached Quran corpus with {len(self.ayahs)} ayahs")
        return self.ayahs

    def _merge_editions(
        self, editions: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Zip the three parallel per-surah/per-ayah edition responses into
        one flat list of merged ayah records, keyed "surah:ayah"."""
        merged = []
        for s_uth, s_simple, s_trans in zip(
            editions["uthmani"], editions["simple"], editions["translation_en"]
        ):
            for a_uth, a_simple, a_trans in zip(
                s_uth["ayahs"], s_simple["ayahs"], s_trans["ayahs"]
            ):
                text_uthmani = a_uth["text"]
                text_simple = a_simple["text"]
                basmalah = None

                if (
                    a_uth["numberInSurah"] == 1
                    and s_uth["number"] not in SURAHS_WITHOUT_LEADING_BASMALAH
                ):
                    basmalah, text_uthmani, text_simple = self._split_leading_basmalah(
                        text_uthmani, text_simple
                    )

                merged.append({
                    "surah_number": s_uth["number"],
                    "surah_name_ar": s_uth["name"],
                    "surah_name_en": s_uth["englishName"],
                    "surah_name_translation_en": s_uth["englishNameTranslation"],
                    "revelation_type": s_uth["revelationType"],
                    "ayah_number": a_uth["numberInSurah"],
                    "global_ayah_number": a_uth["number"],
                    "juz": a_uth["juz"],
                    "page": a_uth["page"],
                    "text_uthmani": text_uthmani,
                    "text_simple": text_simple,
                    "basmalah": basmalah,
                    "translation_en": a_trans["text"],
                    "key": f"{s_uth['number']}:{a_uth['numberInSurah']}",
                })
        return merged

    @staticmethod
    def _split_leading_basmalah(text_uthmani: str, text_simple: str):
        """Detect the Basmalah on the diacritic-free `text_simple` (a
        reliable exact match), then strip the same leading word count from
        both `text_uthmani` and `text_simple`. Returns
        (basmalah_uthmani_or_None, remaining_uthmani, remaining_simple) --
        if the simple text doesn't start with the expected Basmalah (an
        edition/encoding surprise), both texts are returned unchanged rather
        than risking a bad split."""
        simple_words = text_simple.lstrip("﻿ \t").split()
        if " ".join(simple_words[:BASMALAH_WORD_COUNT]) != BASMALAH_SIMPLE:
            return None, text_uthmani, text_simple

        uthmani_words = text_uthmani.lstrip("﻿ \t").split()
        basmalah_uthmani = " ".join(uthmani_words[:BASMALAH_WORD_COUNT])
        remaining_uthmani = " ".join(uthmani_words[BASMALAH_WORD_COUNT:])
        remaining_simple = " ".join(simple_words[BASMALAH_WORD_COUNT:])
        return basmalah_uthmani, remaining_uthmani, remaining_simple

    def _index_by_key(self):
        self._by_key = {ayah["key"]: ayah for ayah in self.ayahs}

    def get_ayah(self, surah: int, ayah: int) -> Optional[Dict[str, Any]]:
        return self._by_key.get(f"{surah}:{ayah}")

    def get_all_ayahs(self) -> List[Dict[str, Any]]:
        return self.ayahs
