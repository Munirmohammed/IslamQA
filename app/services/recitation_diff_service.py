"""
Recitation Diff Service
Compares an ASR transcript of a user's recitation against the canonical ayah
text and classifies each difference as a mistake -- incorrect (substituted),
missed (dropped), or extra (inserted) word -- matching the vocabulary used by
Tarteel's mistake-detection UI.

Normalization here is intentionally *not* TextPreprocessor.preprocess_arabic
(ml_service.py): that preprocessor also strips stopwords and words <=2
characters, which is correct for Q&A search relevance but would silently
drop legitimate short Quranic words (e.g. "في", "من") from the word lists
being aligned here, producing false "missing word" mistakes. This reuses the
same underlying pyarabic normalization calls, just without that tail.
"""

import difflib
from typing import Any, Dict, List

import pyarabic.araby as araby

MistakeType = str  # "incorrect" | "missed" | "extra"


def normalize_for_diff(text: str) -> str:
    """Character-level normalization only (diacritics, tatweel, alef/teh
    variants) -- every word is preserved, unlike TextPreprocessor's search
    preprocessing."""
    text = araby.strip_diacritics(text)
    text = araby.strip_tatweel(text)
    text = araby.normalize_alef(text)
    text = araby.normalize_teh(text)
    return text.strip()


def diff_recitation(canonical_text: str, recited_text: str) -> List[Dict[str, Any]]:
    """Word-align `recited_text` against `canonical_text` and return a list
    of mistakes. Matching stretches ('equal' opcodes) are omitted -- callers
    that want the full aligned transcript (e.g. for highlighting) can
    recompute it, but the mistake-report use case only needs the deltas.
    """
    canonical_words = normalize_for_diff(canonical_text).split()
    recited_words = normalize_for_diff(recited_text).split()

    matcher = difflib.SequenceMatcher(None, canonical_words, recited_words)

    mistakes: List[Dict[str, Any]] = []
    for tag, c_start, c_end, r_start, r_end in matcher.get_opcodes():
        if tag == "equal":
            continue

        if tag == "replace":
            mistakes.append({
                "type": "incorrect",
                "expected": " ".join(canonical_words[c_start:c_end]),
                "recited": " ".join(recited_words[r_start:r_end]),
                "position": c_start,
            })
        elif tag == "delete":
            mistakes.append({
                "type": "missed",
                "expected": " ".join(canonical_words[c_start:c_end]),
                "recited": "",
                "position": c_start,
            })
        elif tag == "insert":
            mistakes.append({
                "type": "extra",
                "expected": "",
                "recited": " ".join(recited_words[r_start:r_end]),
                "position": c_start,
            })

    return mistakes
