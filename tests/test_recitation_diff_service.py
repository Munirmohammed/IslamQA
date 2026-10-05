"""
Recitation Diff Service Tests
Covers word-level alignment between a canonical ayah and a recited
transcript across all three mistake types, independent of the ASR model.
"""

from app.services.recitation_diff_service import diff_recitation, normalize_for_diff


class TestNormalizeForDiff:
    def test_strips_diacritics_but_keeps_every_word(self):
        """Unlike TextPreprocessor.preprocess_arabic, short/common words
        must survive -- they're not noise here, they're part of what's
        being checked."""
        result = normalize_for_diff("قُلْ هُوَ اللَّهُ أَحَدٌ")
        words = result.split()
        assert len(words) == 4
        assert "هو" in words  # a 2-letter word that preprocess_arabic would drop


class TestDiffRecitation:
    def test_exact_match_has_no_mistakes(self):
        mistakes = diff_recitation("قل هو الله احد", "قل هو الله احد")
        assert mistakes == []

    def test_diacritic_only_differences_are_not_mistakes(self):
        """ASR output is typically fully diacritized; the canonical
        'simple' text isn't -- that alone shouldn't count as a mistake."""
        mistakes = diff_recitation("قل هو الله احد", "قُلْ هُوَ اللَّهُ أَحَدٌ")
        assert mistakes == []

    def test_substituted_word_is_incorrect(self):
        mistakes = diff_recitation("قل هو الله احد", "قل هو الرحمن احد")
        assert len(mistakes) == 1
        assert mistakes[0]["type"] == "incorrect"
        assert mistakes[0]["expected"] == "الله"
        assert mistakes[0]["recited"] == "الرحمن"

    def test_dropped_word_is_missed(self):
        mistakes = diff_recitation("قل هو الله احد", "قل الله احد")
        assert len(mistakes) == 1
        assert mistakes[0]["type"] == "missed"
        assert mistakes[0]["expected"] == "هو"
        assert mistakes[0]["recited"] == ""

    def test_added_word_is_extra(self):
        mistakes = diff_recitation("قل هو الله احد", "قل هو والله الله احد")
        assert len(mistakes) == 1
        assert mistakes[0]["type"] == "extra"
        assert mistakes[0]["recited"] == "والله"

    def test_multiple_mistake_types_in_one_recitation(self):
        # canonical: قل هو الله احد
        # recited:   قل الرحمن احد زائد   (missed "هو", substituted "الله"->"الرحمن", extra "زائد")
        mistakes = diff_recitation("قل هو الله احد", "قل الرحمن احد زائد")
        types = [m["type"] for m in mistakes]
        assert "missed" in types or "incorrect" in types
        assert "extra" in types
