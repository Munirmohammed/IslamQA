"""
Daily Islamic content endpoints — hadith, ayah, dua, prayer times, hijri date.
The service holds curated pools and rotates selections deterministically per day.
"""

from typing import Any, Dict, List, Optional
from datetime import date
from fastapi import APIRouter, HTTPException, Query

from app.services.daily_content import DailyContentService

router = APIRouter()

_service = DailyContentService()


@router.get("/today")
def get_today_bundle() -> Dict[str, Any]:
    return _service.get_today_bundle()


@router.get("/hadith")
def get_daily_hadith() -> Dict[str, Any]:
    return _service.get_daily_hadith()


@router.get("/ayah")
def get_daily_ayah() -> Dict[str, Any]:
    return _service.get_daily_ayah()


@router.get("/dua")
def get_daily_dua() -> Dict[str, Any]:
    return _service.get_daily_dua()


@router.get("/hijri")
def get_hijri_date() -> Dict[str, Any]:
    return _service.get_hijri_date()


@router.get("/prayer-times")
def get_prayer_times(
    city: Optional[str] = Query(default=None, description="Filter to a single city by name"),
    method: str = Query(default="MWL", description="Calculation method: MWL, ISNA, Egypt, Makkah, Karachi"),
) -> List[Dict[str, Any]]:
    rows = _service.get_prayer_times_for_cities(method=method)
    if city:
        rows = [r for r in rows if r["city"].lower() == city.lower()]
        if not rows:
            raise HTTPException(status_code=404, detail=f"City '{city}' not found in daily pool")
    return rows


@router.get("/pool/hadith")
def get_full_hadith_pool() -> List[Dict[str, Any]]:
    return _service._hadiths


@router.get("/pool/ayah")
def get_full_ayah_pool() -> List[Dict[str, Any]]:
    return _service._ayahs


@router.get("/pool/dua")
def get_full_dua_pool() -> List[Dict[str, Any]]:
    return _service._duas
