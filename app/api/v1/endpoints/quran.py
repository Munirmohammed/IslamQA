"""
Quran metadata endpoints — list/get/search surahs.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "quran" / "surahs_meta.json"
with open(_DATA, "r", encoding="utf-8") as _f:
    _SURAHS: List[Dict[str, Any]] = json.load(_f)


@router.get("/surahs")
def list_surahs(
    revelation_place: Optional[str] = Query(default=None, description="Meccan or Medinan"),
) -> List[Dict[str, Any]]:
    if revelation_place:
        return [s for s in _SURAHS if s["revelation_place"].lower() == revelation_place.lower()]
    return _SURAHS


@router.get("/surahs/search")
def search_surahs(q: str = Query(..., min_length=1)) -> List[Dict[str, Any]]:
    needle = q.lower()
    return [
        s for s in _SURAHS
        if needle in s["name_en"].lower()
        or needle in s["transliteration"].lower()
        or needle in s["meaning_en"].lower()
    ]


@router.get("/surahs/{number}")
def get_surah(number: int) -> Dict[str, Any]:
    if number < 1 or number > 114:
        raise HTTPException(status_code=404, detail="Surah number must be between 1 and 114")
    return _SURAHS[number - 1]


@router.get("/stats")
def quran_stats() -> Dict[str, Any]:
    return {
        "total_surahs": len(_SURAHS),
        "total_ayahs": sum(s["ayah_count"] for s in _SURAHS),
        "meccan_count": sum(1 for s in _SURAHS if s["revelation_place"] == "Meccan"),
        "medinan_count": sum(1 for s in _SURAHS if s["revelation_place"] == "Medinan"),
    }
