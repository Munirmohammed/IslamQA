"""
Tafsir Service Tests
Covers the chapter-block-grouping logic (hand-built payloads + the real
fetched Al-Ikhlas 112:1-4 chapter, checked into
tests/fixtures/tafsir/112.json) and strip_html, without hitting the live
api.quran.com API.
"""

import json
import os

import pytest

from app.services.tafsir_service import TafsirService, _build_blocks_for_chapter, strip_html

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "tafsir", "112.json")


def load_fixture_verses():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)["tafsirs"]


class TestBuildBlocksForChapter:
    def test_single_ungrouped_ayah(self):
        verses = [{"verse_key": "9:1", "text": "commentary for ayah 1"}]
        by_key = _build_blocks_for_chapter(9, verses)
        assert by_key["9:1"]["ayah_from"] == 1
        assert by_key["9:1"]["ayah_to"] == 1
        assert by_key["9:1"]["text_html"] == "commentary for ayah 1"

    def test_multi_ayah_group_shares_one_block(self):
        verses = [
            {"verse_key": "112:1", "text": "shared commentary"},
            {"verse_key": "112:2", "text": ""},
            {"verse_key": "112:3", "text": ""},
            {"verse_key": "112:4", "text": ""},
        ]
        by_key = _build_blocks_for_chapter(112, verses)

        for ayah in (1, 2, 3, 4):
            block = by_key[f"112:{ayah}"]
            assert block["ayah_from"] == 1
            assert block["ayah_to"] == 4
            assert block["text_html"] == "shared commentary"

    def test_chapter_with_two_separate_groups(self):
        verses = [
            {"verse_key": "5:1", "text": "first group"},
            {"verse_key": "5:2", "text": ""},
            {"verse_key": "5:3", "text": "second group"},
            {"verse_key": "5:4", "text": ""},
            {"verse_key": "5:5", "text": ""},
        ]
        by_key = _build_blocks_for_chapter(5, verses)

        assert by_key["5:1"]["ayah_to"] == 2
        assert by_key["5:2"]["ayah_from"] == 1
        assert by_key["5:3"]["ayah_from"] == 3
        assert by_key["5:3"]["ayah_to"] == 5
        assert by_key["5:5"]["text_html"] == "second group"

    def test_middle_of_group_resolves_to_the_shared_block(self):
        """A commonly-missed edge case: asking about an ayah in the
        *middle* of a group (not its first ayah) must still return the
        group's shared commentary, not an empty block."""
        verses = [
            {"verse_key": "112:1", "text": "shared commentary"},
            {"verse_key": "112:2", "text": ""},
            {"verse_key": "112:3", "text": ""},
        ]
        by_key = _build_blocks_for_chapter(112, verses)
        assert by_key["112:3"]["text_html"] == "shared commentary"
        assert by_key["112:3"]["ayah_from"] == 1


class TestBuildBlocksRealFixture:
    def test_al_ikhlas_grouped_as_one_block(self):
        verses = load_fixture_verses()
        by_key = _build_blocks_for_chapter(112, verses)

        assert len(by_key) == 4
        for ayah in (1, 2, 3, 4):
            block = by_key[f"112:{ayah}"]
            assert block["ayah_from"] == 1
            assert block["ayah_to"] == 4
            assert len(block["text_html"]) > 1000  # the real ~14000-char commentary


class TestStripHtml:
    def test_strips_tags_and_keeps_text(self):
        assert strip_html("<p>Hello</p>") == "Hello"

    def test_separates_paragraphs_with_blank_line(self):
        result = strip_html("<p>First</p><p>Second</p>")
        assert result == "First\n\nSecond"

    def test_real_al_ikhlas_tafsir_strips_cleanly(self):
        verses = load_fixture_verses()
        html = verses[0]["text"]
        plain = strip_html(html)
        assert "<" not in plain
        assert "Ubayy bin Ka" in plain  # a known phrase from the real commentary


class TestGetAyahTafsirFallback:
    def test_unknown_ayah_returns_none(self):
        service = TafsirService(corpus_path="unused")
        service._by_key = {}
        assert service.get_ayah_tafsir(999, 999) is None

    def test_known_ayah_returns_block(self):
        service = TafsirService(corpus_path="unused")
        service._by_key = {"112:1": {"surah_number": 112, "ayah_from": 1, "ayah_to": 4, "text_html": "x", "text_plain": "x"}}
        result = service.get_ayah_tafsir(112, 1)
        assert result["ayah_to"] == 4
