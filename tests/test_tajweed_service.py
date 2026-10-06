"""
Tajweed Service Tests
Covers the HTML-markup parser (hand-built cases + the real fetched
Al-Ikhlas 112:1-4 markup, checked into tests/fixtures/tajweed/112.json) and
the unrecognized-rule-class fallback, without hitting the live
api.quran.com API.
"""

import json
import os
import re

import pytest

from app.services.tajweed_service import TAJWEED_RULE_INFO, TajweedService, parse_tajweed_markup

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "tajweed", "112.json")


def _reference_plain_text(markup: str) -> str:
    """Ground truth derived independently of parse_tajweed_markup (by
    simple tag-stripping) rather than a hand-typed literal: Arabic combining
    marks (e.g. shaddah + fatha on the same letter) can be validly stored in
    more than one order, so a manually retyped expected string risks a
    byte-level mismatch against the real API data despite being visually/
    phonetically identical."""
    without_end_span = re.sub(r"<span class=end>.*?</span>", "", markup)
    without_tajweed_tags = re.sub(r"</?tajweed[^>]*>", "", without_end_span)
    return without_tajweed_tags.strip()


def load_fixture_verses():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)["verses"]


class TestParseTajweedMarkupHandBuilt:
    def test_plain_text_strips_all_tags(self):
        result = parse_tajweed_markup("ا<tajweed class=qalaqah>ب</tajweed>ج")
        assert result["plain_text"] == "ابج"

    def test_rule_span_maps_to_correct_substring(self):
        result = parse_tajweed_markup("ا<tajweed class=qalaqah>ب</tajweed>ج")
        assert len(result["rules"]) == 1
        rule = result["rules"][0]
        assert rule["rule"] == "qalaqah"
        assert rule["text"] == "ب"
        assert result["plain_text"][rule["start"]:rule["end"]] == "ب"

    def test_adjacent_non_nested_tags_both_captured(self):
        result = parse_tajweed_markup(
            "<tajweed class=ham_wasl>ا</tajweed><tajweed class=laam_shamsiyah>ل</tajweed>ص"
        )
        rules_by_class = {r["rule"]: r["text"] for r in result["rules"]}
        assert rules_by_class == {"ham_wasl": "ا", "laam_shamsiyah": "ل"}

    def test_end_span_marker_is_dropped_entirely(self):
        result = parse_tajweed_markup("ابج <span class=end>١</span>")
        assert result["plain_text"] == "ابج"
        assert result["rules"] == []

    def test_multi_character_rule_span(self):
        result = parse_tajweed_markup("ا<tajweed class=idgham_wo_ghunnah>بجد</tajweed>ه")
        assert result["rules"][0]["text"] == "بجد"


class TestParseTajweedMarkupRealFixture:
    """Against the real fetched markup for Al-Ikhlas 112:1-4."""

    def test_112_1_has_ham_wasl_and_qalaqah(self):
        verses = load_fixture_verses()
        verse = next(v for v in verses if v["verse_key"] == "112:1")
        result = parse_tajweed_markup(verse["text_uthmani_tajweed"])

        assert result["plain_text"] == _reference_plain_text(verse["text_uthmani_tajweed"])
        rules_by_class = {r["rule"]: r["text"] for r in result["rules"]}
        assert rules_by_class == {"ham_wasl": "ٱ", "qalaqah": "د"}

    def test_112_2_has_ham_wasl_laam_shamsiyah_and_qalaqah(self):
        verses = load_fixture_verses()
        verse = next(v for v in verses if v["verse_key"] == "112:2")
        result = parse_tajweed_markup(verse["text_uthmani_tajweed"])

        assert result["plain_text"] == _reference_plain_text(verse["text_uthmani_tajweed"])
        rules = [r["rule"] for r in result["rules"]]
        assert rules == ["ham_wasl", "laam_shamsiyah", "qalaqah"]

    def test_all_rule_spans_match_their_recorded_text(self):
        """Every rule's (start, end) slice of plain_text must equal its own
        recorded 'text' -- the real end-to-end offset-correctness check."""
        for verse in load_fixture_verses():
            result = parse_tajweed_markup(verse["text_uthmani_tajweed"])
            for rule in result["rules"]:
                assert result["plain_text"][rule["start"]:rule["end"]] == rule["text"]


class TestUnrecognizedRuleFallback:
    def test_unknown_rule_class_falls_back_without_raising(self):
        service = TajweedService(corpus_path="unused")
        service._by_key = {
            "1:1": {"plain_text": "ابج", "rules": [{"rule": "some_future_rule", "start": 0, "end": 1, "text": "ا"}]}
        }
        annotated = service.get_ayah_tajweed(1, 1)
        assert annotated["rules"][0]["name"] == "some_future_rule"
        assert annotated["rules"][0]["description"] is None

    def test_known_rule_gets_enriched_name_and_description(self):
        service = TajweedService(corpus_path="unused")
        service._by_key = {
            "1:1": {"plain_text": "ابج", "rules": [{"rule": "qalaqah", "start": 0, "end": 1, "text": "ا"}]}
        }
        annotated = service.get_ayah_tajweed(1, 1)
        assert annotated["rules"][0]["name"] == TAJWEED_RULE_INFO["qalaqah"]["name"]
        assert annotated["rules"][0]["description"] == TAJWEED_RULE_INFO["qalaqah"]["description"]

    def test_unknown_ayah_returns_none(self):
        service = TajweedService(corpus_path="unused")
        service._by_key = {}
        assert service.get_ayah_tajweed(999, 999) is None
