"""
Tajweed Rule Annotation Service
Surfaces which tajweed rule applies to which letters in an ayah, sourced
from Quran.com's own public v4 API (api.quran.com/api/v4/quran/verses/
uthmani_tajweed) -- the same tajweed-coloring data Quran.com's own reader
uses. Rule-based only (no audio): this does not measure a user's actual
recitation against these rules -- that's flagged in the roadmap as a
separate, later, research-grade stretch.

Same load-or-fetch disk-cache pattern as quran_corpus_service.py, but kept
as an independent cache rather than merged into it or cross-applied onto
Phase 1's text_uthmani: this is a different upstream source (Quran.com, not
alquran.cloud), and the two Uthmani strings could differ in minor
rendering details (small signs etc.) that would silently misalign a rule
span's character offsets if cross-applied.
"""

import json
import os
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

import requests
import structlog

logger = structlog.get_logger()

CORPUS_PATH = "data/quran/tajweed_corpus.json"
BASE_URL = "https://api.quran.com/api/v4/quran/verses/uthmani_tajweed"
CHAPTER_COUNT = 114

# Catalogued directly from real API responses. An initial 8-chapter sample
# (Al-Fatiha, Al-Baqara, Ya-Sin, Ar-Rahman, Al-Mulk, the three Quls/An-Nas)
# found 16 of these; a subsequent full 114-chapter ingestion run surfaced
# exactly one more (idgham_mutaqaribayn) and confirmed no others exist
# anywhere in the Quran -- see Phase 5 plan notes. Any rule class a future
# re-ingestion encounters outside this set still falls back to a generic
# entry rather than raising (defensive, in case the upstream API's rule set
# ever changes).
TAJWEED_RULE_INFO: Dict[str, Dict[str, str]] = {
    "ham_wasl": {"name": "Hamzat ul-Wasl", "description": "A connecting hamza, silent unless starting speech."},
    "qalaqah": {"name": "Qalqalah", "description": "A slight bounce/echo on ق ط ب ج د when it has sukoon."},
    "madda_normal": {"name": "Madd Tabee'i (Natural Madd)", "description": "Natural elongation, held 2 counts."},
    "madda_permissible": {"name": "Madd Jaiz (Permissible Madd)", "description": "Elongation that may be held 2, 4, or 6 counts."},
    "madda_necessary": {"name": "Madd Laazim (Necessary Madd)", "description": "Elongation held 6 counts, mandatory."},
    "madda_obligatory": {"name": "Madd Wajib Muttasil (Obligatory Madd)", "description": "Elongation held 4-5 counts, madd letter followed by hamza in the same word."},
    "laam_shamsiyah": {"name": "Lam Shamsiyyah", "description": "The lam of ال assimilates into a following sun letter and isn't pronounced."},
    "ghunnah": {"name": "Ghunnah", "description": "A nasal sound held 2 counts, typically on a noon or meem with shaddah."},
    "idgham_ghunnah": {"name": "Idgham with Ghunnah", "description": "A noon sakinah/tanween merges into the next letter with a nasal sound."},
    "idgham_wo_ghunnah": {"name": "Idgham without Ghunnah", "description": "A noon sakinah/tanween merges into the next letter without a nasal sound."},
    "idgham_shafawi": {"name": "Idgham Shafawi", "description": "A meem sakinah merges into a following meem."},
    "idgham_mutajanisayn": {"name": "Idgham Mutajanisayn", "description": "Two letters sharing the same articulation point but differing in a characteristic merge together."},
    "idgham_mutaqaribayn": {"name": "Idgham Mutaqaribayn", "description": "Two letters with close (but not identical) articulation points and characteristics merge together."},
    "ikhafa": {"name": "Ikhfa", "description": "A nasalized, concealed pronunciation of a noon sakinah/tanween before certain letters."},
    "ikhafa_shafawi": {"name": "Ikhfa Shafawi", "description": "A nasalized, concealed pronunciation of a meem sakinah before ب."},
    "iqlab": {"name": "Iqlab", "description": "A noon sakinah/tanween is converted to a meem sound before ب."},
    "slnt": {"name": "Silent Letter", "description": "A letter that is written but not pronounced."},
}


class _TajweedHTMLParser(HTMLParser):
    """Recovers the plain Uthmani text and each rule's character span from
    Quran.com's `<tajweed class=...>segment</tajweed>` markup. The
    `<span class=end>...</span>` ayah-ending numeral marker's content is
    dropped entirely (redundant -- ayah numbers are already tracked)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: List[str] = []
        self.rules: List[Tuple[str, int, int]] = []
        self._open_rule: Optional[Tuple[str, int]] = None
        self._skip_depth = 0

    @property
    def _pos(self) -> int:
        return sum(len(p) for p in self._parts)

    def handle_starttag(self, tag: str, attrs):
        attrs_dict = dict(attrs)
        if tag == "tajweed":
            self._open_rule = (attrs_dict.get("class", ""), self._pos)
        elif tag == "span" and attrs_dict.get("class") == "end":
            self._skip_depth += 1

    def handle_endtag(self, tag: str):
        if tag == "tajweed" and self._open_rule:
            rule_class, start = self._open_rule
            self.rules.append((rule_class, start, self._pos))
            self._open_rule = None
        elif tag == "span" and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str):
        if self._skip_depth == 0:
            self._parts.append(data)

    @property
    def plain_text(self) -> str:
        return "".join(self._parts)


def parse_tajweed_markup(markup: str) -> Dict[str, Any]:
    """Parse one ayah's `text_uthmani_tajweed` markup into
    {"plain_text": str, "rules": [{"rule", "start", "end", "text"}]}."""
    parser = _TajweedHTMLParser()
    parser.feed(markup)

    raw_text = parser.plain_text
    stripped_left = raw_text.lstrip()
    left_shift = len(raw_text) - len(stripped_left)
    plain_text = stripped_left.rstrip()

    rules = []
    for rule_class, start, end in parser.rules:
        adj_start, adj_end = start - left_shift, end - left_shift
        rules.append({
            "rule": rule_class,
            "start": adj_start,
            "end": adj_end,
            "text": plain_text[adj_start:adj_end],
        })

    return {"plain_text": plain_text, "rules": rules}


def _enrich_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    info = TAJWEED_RULE_INFO.get(rule["rule"])
    return {
        **rule,
        "name": info["name"] if info else rule["rule"],
        "description": info["description"] if info else None,
    }


class TajweedService:
    """Loads and serves the per-ayah tajweed rule annotations."""

    def __init__(self, corpus_path: str = CORPUS_PATH):
        self.corpus_path = corpus_path
        self._by_key: Dict[str, Dict[str, Any]] = {}

    def load_or_fetch(self, force_refetch: bool = False) -> Dict[str, Dict[str, Any]]:
        if not force_refetch and os.path.exists(self.corpus_path):
            try:
                with open(self.corpus_path, encoding="utf-8") as f:
                    self._by_key = json.load(f)
                logger.info(f"Loaded cached tajweed corpus with {len(self._by_key)} ayahs")
                return self._by_key
            except Exception:
                logger.warning("Failed to load cached tajweed corpus, refetching...")

        logger.info("Fetching tajweed corpus from api.quran.com...")
        by_key: Dict[str, Dict[str, Any]] = {}
        for chapter in range(1, CHAPTER_COUNT + 1):
            response = requests.get(BASE_URL, params={"chapter_number": chapter}, timeout=30)
            response.raise_for_status()
            for verse in response.json()["verses"]:
                surah_str, ayah_str = verse["verse_key"].split(":")
                parsed = parse_tajweed_markup(verse["text_uthmani_tajweed"])
                by_key[f"{surah_str}:{ayah_str}"] = parsed

        self._by_key = by_key
        os.makedirs(os.path.dirname(self.corpus_path), exist_ok=True)
        with open(self.corpus_path, "w", encoding="utf-8") as f:
            json.dump(by_key, f, ensure_ascii=False)

        logger.info(f"Fetched and cached tajweed corpus with {len(by_key)} ayahs")
        return self._by_key

    def get_ayah_tajweed(self, surah: int, ayah: int) -> Optional[Dict[str, Any]]:
        entry = self._by_key.get(f"{surah}:{ayah}")
        if not entry:
            return None
        return {
            "plain_text": entry["plain_text"],
            "rules": [_enrich_rule(r) for r in entry["rules"]],
        }


tajweed_service = TajweedService()
