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
                    "text_uthmani": a_uth["text"],
                    "text_simple": a_simple["text"],
                    "translation_en": a_trans["text"],
                    "key": f"{s_uth['number']}:{a_uth['numberInSurah']}",
                })
        return merged

    def _index_by_key(self):
        self._by_key = {ayah["key"]: ayah for ayah in self.ayahs}

    def get_ayah(self, surah: int, ayah: int) -> Optional[Dict[str, Any]]:
        return self._by_key.get(f"{surah}:{ayah}")

    def get_all_ayahs(self) -> List[Dict[str, Any]]:
        return self.ayahs
