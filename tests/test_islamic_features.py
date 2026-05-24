"""
Smoke tests for the daily content engine, islamic tools, and curated data files.

Runnable directly (`python tests/test_islamic_features.py`) without pytest
or FastAPI — the assertions check the pure-Python service layer and validate
that all data files load cleanly with expected counts and schema.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.daily_content import DailyContentService  # noqa: E402
from app.services.islamic_tools import (  # noqa: E402
    calc_prayer_times,
    calc_qibla,
    calc_zakat,
    gregorian_from_hijri,
    hijri_from_gregorian,
)

DATA = ROOT / "data"


# ── Data file integrity ────────────────────────────────────────────────────


def _load(p: Path) -> list:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def test_hadith_pool_has_min_entries_and_required_fields():
    pool = _load(DATA / "daily" / "hadith_pool.json")
    assert len(pool) >= 30, f"hadith pool too small: {len(pool)}"
    required = {"id", "narrator", "text_en", "reference", "grade"}
    for h in pool:
        missing = required - h.keys()
        assert not missing, f"hadith #{h.get('id')} missing fields {missing}"
        assert h["grade"].lower() in {"sahih", "hasan", "sahih/hasan"}, f"weak grade in pool: {h}"


def test_ayah_pool_has_min_entries_and_arabic_text():
    pool = _load(DATA / "daily" / "ayah_pool.json")
    assert len(pool) >= 30
    arabic = re.compile(r"[؀-ۿ]")
    for a in pool:
        assert 1 <= a["surah_number"] <= 114
        assert a["ayah_number"] >= 1
        assert arabic.search(a["text_ar"]), f"no arabic in ayah {a['id']}"


def test_dua_pool_has_min_entries_and_source_attribution():
    pool = _load(DATA / "daily" / "dua_pool.json")
    assert len(pool) >= 20
    for d in pool:
        assert d.get("source"), f"dua {d['id']} missing source attribution"
        assert d.get("text_ar") and d.get("transliteration") and d.get("text_en_translation")


def test_cities_have_valid_coords():
    cities = _load(DATA / "daily" / "cities.json")
    assert len(cities) >= 12
    for c in cities:
        assert -90 <= c["lat"] <= 90 and -180 <= c["lon"] <= 180
        assert -12 <= c["timezone_offset"] <= 14


def test_quran_meta_is_complete_and_canonical():
    surahs = _load(DATA / "quran" / "surahs_meta.json")
    assert len(surahs) == 114
    total_ayahs = sum(s["ayah_count"] for s in surahs)
    assert total_ayahs == 6236, f"expected 6236 ayahs, got {total_ayahs}"
    for i, s in enumerate(surahs, start=1):
        assert s["number"] == i
        assert s["revelation_place"] in {"Meccan", "Medinan"}


def test_99_names_is_complete():
    names = _load(DATA / "names" / "asma_ul_husna.json")
    assert len(names) == 99
    for i, n in enumerate(names, start=1):
        assert n["number"] == i
        assert n["name_ar"] and n["transliteration"] and n["meaning_en"]
    assert names[0]["transliteration"] == "Ar-Rahman"
    assert names[1]["transliteration"] == "Ar-Rahim"


# ── DailyContentService ────────────────────────────────────────────────────


def test_daily_selection_is_deterministic_per_date():
    s = DailyContentService()
    d = date(2026, 5, 24)
    h1 = s.get_daily_hadith(d)
    h2 = s.get_daily_hadith(d)
    assert h1["id"] == h2["id"], "same date must yield same hadith"
    # Different date should usually yield different selection (not strict equality test,
    # but at least one of the three should differ across a week).
    bundles = [
        (s.get_daily_hadith(date(2026, 5, 24 + i))["id"],
         s.get_daily_ayah(date(2026, 5, 24 + i))["id"]) for i in range(7)
    ]
    assert len(set(bundles)) > 1


def test_hijri_today_is_in_1447_or_1448():
    s = DailyContentService()
    h = s.get_hijri_date()
    assert h["year"] in (1447, 1448), f"unexpected hijri year for 2026 Gregorian: {h['year']}"
    assert 1 <= h["month"] <= 12


def test_prayer_times_return_valid_hhmm_for_all_cities():
    s = DailyContentService()
    rows = s.get_prayer_times_for_cities()
    pattern = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
    for r in rows:
        for key in ("fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"):
            assert pattern.match(r["times"][key]), \
                f"bad time in {r['city']}.{key}: {r['times'][key]}"


def test_today_bundle_shape():
    bundle = DailyContentService().get_today_bundle()
    for key in ("gregorian_date", "hijri_date", "hadith", "ayah", "dua", "prayer_times", "generated_at"):
        assert key in bundle, f"bundle missing {key}"


# ── islamic_tools ──────────────────────────────────────────────────────────


def test_qibla_known_cities():
    # NYC → Kaaba: well-known bearing ~58°.
    q = calc_qibla(40.7128, -74.0060)
    assert 56 <= q["bearing_degrees"] <= 60, f"NYC qibla off: {q}"
    assert 10000 <= q["distance_km"] <= 11000
    # London → Kaaba: ~119°.
    q = calc_qibla(51.5074, -0.1278)
    assert 117 <= q["bearing_degrees"] <= 121
    # Jakarta → Kaaba: ~295° (north-west).
    q = calc_qibla(-6.2088, 106.8456)
    assert 290 <= q["bearing_degrees"] <= 300


def test_hijri_gregorian_round_trip():
    g = date(2026, 5, 24)
    h = hijri_from_gregorian(g)
    back = gregorian_from_hijri(h["year"], h["month"], h["day"])
    assert (back["year"], back["month"], back["day"]) == (g.year, g.month, g.day)


def test_zakat_below_nisab_yields_zero():
    r = calc_zakat(cash=100)
    assert r["zakat_due"] == 0
    assert r["is_eligible"] is False


def test_zakat_above_nisab_is_2_5_percent():
    r = calc_zakat(cash=10000)
    assert r["is_eligible"] is True
    assert r["zakat_due"] == 250.0  # 2.5% of 10000


def test_prayer_times_for_mecca_summer_have_pre_dawn_fajr():
    t = calc_prayer_times(21.4225, 39.8262, date(2026, 6, 21), timezone_offset=3, method="Makkah")
    # Summer Fajr in Mecca is roughly 04:00-04:30.
    fajr_h, fajr_m = map(int, t["fajr"].split(":"))
    assert 3 <= fajr_h <= 5, f"unexpected Mecca summer Fajr: {t['fajr']}"


# ── Standalone runner ──────────────────────────────────────────────────────


def _discover_and_run():
    funcs = [(name, obj) for name, obj in globals().items()
             if name.startswith("test_") and callable(obj)]
    passed = failed = 0
    for name, fn in funcs:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed (out of {len(funcs)})")
    return failed


if __name__ == "__main__":
    sys.exit(_discover_and_run())
