"""
Islamic utility calculations: prayer times for any coordinates, Qibla bearing
to the Kaaba, Hijri ↔ Gregorian conversion, and Zakat liability.

All functions are pure (no DB / network). Prayer time math is derived from
Meeus' Astronomical Algorithms — same approach as PrayTimes.org. Qibla uses
the standard great-circle initial-bearing formula. Hijri conversion uses the
tabular Islamic calendar (epoch JDN 1948440).
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, Optional

KAABA_LAT = 21.4225
KAABA_LON = 39.8262

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

_METHODS = {
    "MWL": {"fajr": 18.0, "isha": 17.0, "isha_minutes": None},
    "ISNA": {"fajr": 15.0, "isha": 15.0, "isha_minutes": None},
    "Egypt": {"fajr": 19.5, "isha": 17.5, "isha_minutes": None},
    "Makkah": {"fajr": 18.5, "isha": 0.0, "isha_minutes": 90},
    "Karachi": {"fajr": 18.0, "isha": 18.0, "isha_minutes": None},
}


def _gregorian_to_jdn(y: int, m: int, d: int) -> int:
    a = (14 - m) // 12
    y2 = y + 4800 - a
    m2 = m + 12 * a - 3
    return d + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - y2 // 100 + y2 // 400 - 32045


def _jdn_to_gregorian(jd: int) -> tuple:
    a = jd + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


def _jdn_to_hijri(jd: int) -> tuple:
    l = jd - 1948440 + 10632
    n = (l - 1) // 10631
    l = l - 10631 * n + 354
    j = ((10985 - l) // 5316) * ((50 * l) // 17719) + (l // 5670) * ((43 * l) // 15238)
    l = l - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
    m = (24 * l) // 709
    d = l - (709 * m) // 24
    y = 30 * n + j - 30
    return int(y), int(m), int(d)


def _hijri_to_jdn(y: int, m: int, d: int) -> int:
    return (
        d + math.ceil(29.5 * (m - 1)) + (y - 1) * 354 + (3 + 11 * y) // 30 + 1948440 - 1
    )


def calc_prayer_times(
    lat: float,
    lon: float,
    g_date: Optional[date] = None,
    timezone_offset: float = 0.0,
    method: str = "MWL",
    asr_method: str = "shafi",
) -> Dict[str, str]:
    d = g_date or date.today()
    params = _METHODS.get(method, _METHODS["MWL"])
    shadow_factor = 2 if asr_method.lower() == "hanafi" else 1

    jd = _gregorian_to_jdn(d.year, d.month, d.day) - 0.5
    n = jd - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    decl = math.asin(math.sin(eps) * math.sin(lam))
    eqt = (L - math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam)))) / 15.0
    eqt = ((eqt + 12) % 24) - 12

    lat_r = math.radians(lat)
    dhuhr = 12 - eqt - lon / 15.0 + timezone_offset

    def ha(angle: float) -> Optional[float]:
        cos_h = (-math.sin(math.radians(angle)) - math.sin(lat_r) * math.sin(decl)) / (
            math.cos(lat_r) * math.cos(decl)
        )
        if cos_h < -1 or cos_h > 1:
            return None
        return math.degrees(math.acos(cos_h)) / 15.0

    def asr_ha(sf: int) -> Optional[float]:
        a = math.atan(1.0 / (sf + math.tan(abs(lat_r - decl))))
        cos_h = (math.sin(a) - math.sin(lat_r) * math.sin(decl)) / (
            math.cos(lat_r) * math.cos(decl)
        )
        if cos_h < -1 or cos_h > 1:
            return None
        return math.degrees(math.acos(cos_h)) / 15.0

    sun_h = ha(0.833)
    fajr_h = ha(params["fajr"])
    asr_h = asr_ha(shadow_factor)

    def fmt(t: Optional[float]) -> str:
        if t is None or math.isnan(t):
            return "--:--"
        t = t % 24
        h = int(t)
        m = int(round((t - h) * 60))
        if m == 60:
            m, h = 0, (h + 1) % 24
        return f"{h:02d}:{m:02d}"

    sunrise = dhuhr - sun_h if sun_h is not None else None
    maghrib = dhuhr + sun_h if sun_h is not None else None
    asr = dhuhr + asr_h if asr_h is not None else None
    fajr = dhuhr - fajr_h if fajr_h is not None else None
    if params["isha_minutes"] is not None and maghrib is not None:
        isha = maghrib + params["isha_minutes"] / 60.0
    else:
        isha_h = ha(params["isha"])
        isha = dhuhr + isha_h if isha_h is not None else None

    # High-latitude fallback: 1/7-of-night when astronomical Fajr/Isha undefined.
    if maghrib is not None and sunrise is not None:
        night = (sunrise + 24 - maghrib) % 24
        if fajr is None:
            fajr = sunrise - night / 7.0
        if isha is None:
            isha = maghrib + night / 7.0

    return {
        "fajr": fmt(fajr),
        "sunrise": fmt(sunrise),
        "dhuhr": fmt(dhuhr),
        "asr": fmt(asr),
        "maghrib": fmt(maghrib),
        "isha": fmt(isha),
        "method": method,
        "asr_method": "hanafi" if shadow_factor == 2 else "shafi",
    }


def calc_qibla(lat: float, lon: float) -> Dict[str, Any]:
    lat1, lat2 = math.radians(lat), math.radians(KAABA_LAT)
    dlon = math.radians(KAABA_LON - lon)
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    # Haversine distance to Kaaba
    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance_km = 6371.0 * c
    return {
        "bearing_degrees": round(bearing, 2),
        "distance_km": round(distance_km, 1),
        "kaaba_lat": KAABA_LAT,
        "kaaba_lon": KAABA_LON,
    }


def hijri_from_gregorian(g_date: Optional[date] = None) -> Dict[str, Any]:
    d = g_date or date.today()
    jd = _gregorian_to_jdn(d.year, d.month, d.day)
    y, m, day = _jdn_to_hijri(jd)
    return {
        "day": day,
        "month": m,
        "month_name_en": HIJRI_MONTHS_EN[m - 1],
        "month_name_ar": HIJRI_MONTHS_AR[m - 1],
        "year": y,
        "formatted": f"{day} {HIJRI_MONTHS_EN[m - 1]} {y} AH",
    }


def gregorian_from_hijri(h_year: int, h_month: int, h_day: int) -> Dict[str, Any]:
    jd = _hijri_to_jdn(h_year, h_month, h_day)
    y, m, d = _jdn_to_gregorian(int(jd))
    return {"year": y, "month": m, "day": d, "iso": f"{y:04d}-{m:02d}-{d:02d}"}


def calc_zakat(
    cash: float = 0.0,
    gold_grams: float = 0.0,
    silver_grams: float = 0.0,
    business_assets: float = 0.0,
    debts: float = 0.0,
    gold_price_per_gram: float = 65.0,
    silver_price_per_gram: float = 0.85,
) -> Dict[str, Any]:
    gold_value = gold_grams * gold_price_per_gram
    silver_value = silver_grams * silver_price_per_gram
    total_wealth = cash + gold_value + silver_value + business_assets - debts
    nisab_gold = 87.48 * gold_price_per_gram
    nisab_silver = 612.36 * silver_price_per_gram
    # Silver nisab is the lower threshold and is the scholarly default since
    # it benefits the recipients more — Hanafi position followed by many.
    nisab_used = min(nisab_gold, nisab_silver)
    is_eligible = total_wealth >= nisab_used
    zakat_due = round(total_wealth * 0.025, 2) if is_eligible else 0.0
    return {
        "total_wealth": round(total_wealth, 2),
        "nisab_gold": round(nisab_gold, 2),
        "nisab_silver": round(nisab_silver, 2),
        "nisab_used": round(nisab_used, 2),
        "is_eligible": is_eligible,
        "zakat_due": zakat_due,
        "rate_percent": 2.5,
        "breakdown": {
            "cash": cash,
            "gold_value": round(gold_value, 2),
            "silver_value": round(silver_value, 2),
            "business_assets": business_assets,
            "debts_subtracted": debts,
        },
    }
