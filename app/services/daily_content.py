"""
Daily Islamic content engine.

Picks a hadith, ayah, and dua for the current day from curated pools using
a deterministic day-of-year index so the selection is stable for any given
Hijri/Gregorian date. Also computes prayer times for major cities using
astronomical formulas (Muslim World League method) and converts the current
Gregorian date to Hijri using the tabular Umm al-Qura arithmetic.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "daily"

HIJRI_MONTHS_EN = [
    "Muharram", "Safar", "Rabi al-Awwal", "Rabi al-Thani",
    "Jumada al-Awwal", "Jumada al-Thani", "Rajab", "Sha'ban",
    "Ramadan", "Shawwal", "Dhu al-Qi'dah", "Dhu al-Hijjah",
]
HIJRI_MONTHS_AR = [
    "محرم", "صفر", "ربيع الأول", "ربيع الثاني",
    "جمادى الأولى", "جمادى الثانية", "رجب", "شعبان",
    "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]


def _load(name: str) -> List[Dict[str, Any]]:
    with open(DATA_ROOT / name, "r", encoding="utf-8") as f:
        return json.load(f)


def _day_of_year_index(d: date, pool_size: int) -> int:
    return ((d - date(d.year, 1, 1)).days) % pool_size


class DailyContentService:
    def __init__(self) -> None:
        self._hadiths = _load("hadith_pool.json")
        self._ayahs = _load("ayah_pool.json")
        self._duas = _load("dua_pool.json")
        self._cities = _load("cities.json")

    def get_daily_hadith(self, d: Optional[date] = None) -> Dict[str, Any]:
        d = d or date.today()
        return self._hadiths[_day_of_year_index(d, len(self._hadiths))]

    def get_daily_ayah(self, d: Optional[date] = None) -> Dict[str, Any]:
        d = d or date.today()
        return self._ayahs[_day_of_year_index(d, len(self._ayahs))]

    def get_daily_dua(self, d: Optional[date] = None) -> Dict[str, Any]:
        d = d or date.today()
        return self._duas[_day_of_year_index(d, len(self._duas))]

    # Tabular Islamic calendar — algorithm from Fliegel/Van Flandern style
    # JDN conversion. Accurate to within 1 day of the official Umm al-Qura
    # observation for civil purposes.
    def get_hijri_date(self, g_date: Optional[date] = None) -> Dict[str, Any]:
        d = g_date or date.today()
        jd = self._gregorian_to_jdn(d.year, d.month, d.day)
        h_year, h_month, h_day = self._jdn_to_hijri(jd)
        return {
            "day": h_day,
            "month": h_month,
            "month_name_en": HIJRI_MONTHS_EN[h_month - 1],
            "month_name_ar": HIJRI_MONTHS_AR[h_month - 1],
            "year": h_year,
            "formatted": f"{h_day} {HIJRI_MONTHS_EN[h_month - 1]} {h_year} AH",
        }

    @staticmethod
    def _gregorian_to_jdn(y: int, m: int, d: int) -> int:
        a = (14 - m) // 12
        y2 = y + 4800 - a
        m2 = m + 12 * a - 3
        return d + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - y2 // 100 + y2 // 400 - 32045

    @staticmethod
    def _jdn_to_hijri(jd: int) -> tuple:
        # Tabular Islamic calendar epoch JDN = 1948440 (1 Muharram 1 AH = 16 July 622 CE Julian)
        l = jd - 1948440 + 10632
        n = (l - 1) // 10631
        l = l - 10631 * n + 354
        j = ((10985 - l) // 5316) * ((50 * l) // 17719) + (l // 5670) * ((43 * l) // 15238)
        l = l - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
        m = (24 * l) // 709
        d = l - (709 * m) // 24
        y = 30 * n + j - 30
        return int(y), int(m), int(d)

    def get_prayer_times_for_cities(
        self, d: Optional[date] = None, method: str = "MWL"
    ) -> List[Dict[str, Any]]:
        d = d or date.today()
        return [
            {
                "city": c["name"],
                "country": c["country"],
                "lat": c["lat"],
                "lon": c["lon"],
                "times": self.calc_prayer_times(c["lat"], c["lon"], d, c["timezone_offset"], method),
            }
            for c in self._cities
        ]

    @staticmethod
    def calc_prayer_times(
        lat: float, lon: float, d: date, tz_offset: float, method: str = "MWL"
    ) -> Dict[str, str]:
        # Astronomical formulas adapted from PrayTimes.org reference algorithms,
        # rooted in Meeus' "Astronomical Algorithms" — solar declination, equation
        # of time, and hour-angle solutions for sun depression / altitude.
        params = {
            "MWL": {"fajr": 18.0, "isha": 17.0, "isha_minutes": None},
            "ISNA": {"fajr": 15.0, "isha": 15.0, "isha_minutes": None},
            "Egypt": {"fajr": 19.5, "isha": 17.5, "isha_minutes": None},
            "Makkah": {"fajr": 18.5, "isha": 0.0, "isha_minutes": 90},
            "Karachi": {"fajr": 18.0, "isha": 18.0, "isha_minutes": None},
        }.get(method, {"fajr": 18.0, "isha": 17.0, "isha_minutes": None})

        jd = DailyContentService._gregorian_to_jdn(d.year, d.month, d.day) - 0.5
        n = jd - 2451545.0
        L = (280.460 + 0.9856474 * n) % 360
        g = math.radians((357.528 + 0.9856003 * n) % 360)
        lambda_ = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
        epsilon = math.radians(23.439 - 0.0000004 * n)
        decl = math.asin(math.sin(epsilon) * math.sin(lambda_))
        eqt = (L - math.degrees(math.atan2(math.cos(epsilon) * math.sin(lambda_), math.cos(lambda_)))) / 15.0
        eqt = ((eqt + 12) % 24) - 12

        lat_r = math.radians(lat)
        dhuhr = 12 - eqt - lon / 15.0 + tz_offset

        def hour_angle(angle_deg: float) -> Optional[float]:
            try:
                cos_h = (
                    -math.sin(math.radians(angle_deg)) - math.sin(lat_r) * math.sin(decl)
                ) / (math.cos(lat_r) * math.cos(decl))
                if cos_h < -1 or cos_h > 1:
                    return None
                return math.degrees(math.acos(cos_h)) / 15.0
            except Exception:
                return None

        def asr_hour_angle(shadow_factor: int = 1) -> Optional[float]:
            try:
                a = math.atan(1.0 / (shadow_factor + math.tan(abs(lat_r - decl))))
                cos_h = (math.sin(a) - math.sin(lat_r) * math.sin(decl)) / (
                    math.cos(lat_r) * math.cos(decl)
                )
                if cos_h < -1 or cos_h > 1:
                    return None
                return math.degrees(math.acos(cos_h)) / 15.0
            except Exception:
                return None

        sunrise_h = hour_angle(0.833)
        fajr_h = hour_angle(params["fajr"])
        asr_h = asr_hour_angle(1)

        def fmt(t: Optional[float]) -> str:
            if t is None or math.isnan(t):
                return "--:--"
            t = t % 24
            h = int(t)
            m = int(round((t - h) * 60))
            if m == 60:
                m = 0
                h = (h + 1) % 24
            return f"{h:02d}:{m:02d}"

        fajr = dhuhr - fajr_h if fajr_h is not None else None
        sunrise = dhuhr - sunrise_h if sunrise_h is not None else None
        asr = dhuhr + asr_h if asr_h is not None else None
        maghrib = dhuhr + sunrise_h if sunrise_h is not None else None
        if params["isha_minutes"] is not None and maghrib is not None:
            isha = maghrib + params["isha_minutes"] / 60.0
        else:
            isha_h = hour_angle(params["isha"])
            isha = dhuhr + isha_h if isha_h is not None else None

        return {
            "fajr": fmt(fajr),
            "sunrise": fmt(sunrise),
            "dhuhr": fmt(dhuhr),
            "asr": fmt(asr),
            "maghrib": fmt(maghrib),
            "isha": fmt(isha),
        }

    def get_today_bundle(self, d: Optional[date] = None) -> Dict[str, Any]:
        d = d or date.today()
        return {
            "gregorian_date": d.isoformat(),
            "hijri_date": self.get_hijri_date(d),
            "hadith": self.get_daily_hadith(d),
            "ayah": self.get_daily_ayah(d),
            "dua": self.get_daily_dua(d),
            "prayer_times": self.get_prayer_times_for_cities(d),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
