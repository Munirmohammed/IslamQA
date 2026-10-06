"""
Tafsir Service
Loads Quranic exegesis (tafsir) text per ayah from Quran.com's public v4
API -- "Ibn Kathir (Abridged)" (resource id 169), a well-known, authentic,
English-language classical tafsir. Same load-or-fetch disk-cache pattern as
quran_corpus_service.py/tajweed_service.py.

Real quirk this is designed around: tafsir commentary is written per
*group* of consecutive ayahs, not strictly one ayah at a time. Fetching
Al-Ikhlas (112) confirmed this directly: `by_chapter/112` returns one entry
per ayah, but only 112:1's `text` is non-empty (the shared commentary for
112:1-4); 112:2/3/4 come back with empty text. Ingestion tracks this as
explicit (ayah_from, ayah_to) blocks so every ayah in a group resolves to
the same shared block, carrying that range.
"""

import json
import os
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

import requests
import structlog

logger = structlog.get_logger()

CORPUS_PATH = "data/quran/tafsir_corpus.json"
BASE_URL = "https://api.quran.com/api/v4/tafsirs/{tafsir_id}/by_chapter/{chapter}"
TAFSIR_ID = 169  # Ibn Kathir (Abridged), English
CHAPTER_COUNT = 114
EXPECTED_AYAH_COUNT = 6236

# This endpoint paginates (confirmed: Al-Baqara's 286 ayahs come back only
# 10 per page by default, 29 pages) -- per_page=300 covers even the
# longest surah (286 ayahs) in a single request per chapter, same
# one-request-per-chapter shape as Phase 5's tajweed ingestion.
PER_PAGE = 300


class _PlainTextHTMLParser(HTMLParser):
    """Strips tafsir HTML markup to plain text, preserving paragraph breaks
    so the result stays readable (used for the search-indexed text_plain
    field -- HTML tags would otherwise pollute BM25/embedding tokenization)."""

    BLOCK_END_TAGS = {"p", "h1", "h2", "h3", "li"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: List[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag in self.BLOCK_END_TAGS:
            self._parts.append("\n\n")

    def handle_data(self, data: str):
        self._parts.append(data)

    @property
    def raw_text(self) -> str:
        return "".join(self._parts)


def strip_html(html: str) -> str:
    """Plain-text version of tafsir HTML, paragraphs separated by blank lines."""
    parser = _PlainTextHTMLParser()
    parser.feed(html)
    lines = [line.strip() for line in parser.raw_text.splitlines()]
    return "\n\n".join(line for line in lines if line)


def _build_blocks_for_chapter(chapter_number: int, verses: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Group a chapter's per-ayah tafsir entries into (ayah_from, ayah_to)
    blocks, carrying the last non-empty text forward across empty-text
    ayahs in the same group. `verses` must be in ascending ayah order
    (as returned by the API)."""
    by_key: Dict[str, Dict[str, Any]] = {}
    current_block: Optional[Dict[str, Any]] = None

    for verse in verses:
        _, ayah_str = verse["verse_key"].split(":")
        ayah_num = int(ayah_str)
        text = verse.get("text") or ""

        if text.strip():
            current_block = {
                "surah_number": chapter_number,
                "ayah_from": ayah_num,
                "ayah_to": ayah_num,
                "text_html": text,
            }
        elif current_block is not None:
            current_block["ayah_to"] = ayah_num
        else:
            # No preceding non-empty block in this chapter yet (edge case,
            # not observed in practice but handled defensively): an empty
            # placeholder block rather than skipping the ayah entirely.
            current_block = {
                "surah_number": chapter_number,
                "ayah_from": ayah_num,
                "ayah_to": ayah_num,
                "text_html": "",
            }

        by_key[f"{chapter_number}:{ayah_num}"] = current_block

    return by_key


class TafsirService:
    """Loads and serves per-ayah tafsir blocks."""

    def __init__(self, corpus_path: str = CORPUS_PATH):
        self.corpus_path = corpus_path
        self._by_key: Dict[str, Dict[str, Any]] = {}

    def load_or_fetch(self, force_refetch: bool = False) -> Dict[str, Dict[str, Any]]:
        if not force_refetch and os.path.exists(self.corpus_path):
            try:
                with open(self.corpus_path, encoding="utf-8") as f:
                    self._by_key = json.load(f)
                logger.info(f"Loaded cached tafsir corpus with {len(self._by_key)} ayah entries")
                return self._by_key
            except Exception:
                logger.warning("Failed to load cached tafsir corpus, refetching...")

        logger.info("Fetching tafsir corpus from api.quran.com...")
        by_key: Dict[str, Dict[str, Any]] = {}
        for chapter in range(1, CHAPTER_COUNT + 1):
            response = requests.get(
                BASE_URL.format(tafsir_id=TAFSIR_ID, chapter=chapter),
                params={"per_page": PER_PAGE},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            verses = payload["tafsirs"]

            pagination = payload.get("pagination") or {}
            if pagination.get("next_page"):
                logger.warning(
                    f"Chapter {chapter}: tafsir response still paginated "
                    f"beyond per_page={PER_PAGE} ({pagination}); some ayahs "
                    f"in this chapter will be missing"
                )

            chapter_blocks = _build_blocks_for_chapter(chapter, verses)
            for key, block in chapter_blocks.items():
                by_key[key] = {**block, "text_plain": strip_html(block["text_html"])}

        if len(by_key) != EXPECTED_AYAH_COUNT:
            logger.warning(f"Fetched {len(by_key)} ayah entries, expected {EXPECTED_AYAH_COUNT}")

        self._by_key = by_key
        os.makedirs(os.path.dirname(self.corpus_path), exist_ok=True)
        with open(self.corpus_path, "w", encoding="utf-8") as f:
            json.dump(by_key, f, ensure_ascii=False)

        logger.info(f"Fetched and cached tafsir corpus with {len(by_key)} ayah entries")
        return self._by_key

    def get_ayah_tafsir(self, surah: int, ayah: int) -> Optional[Dict[str, Any]]:
        return self._by_key.get(f"{surah}:{ayah}")

    def get_all_blocks_by_key(self) -> Dict[str, Dict[str, Any]]:
        return self._by_key


tafsir_service = TafsirService()
