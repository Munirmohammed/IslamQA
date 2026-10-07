"""
Quran Content Endpoints
Plain read/browse access to the Quran corpus (Phase 1's QuranCorpusService)
-- surah list and full per-surah ayah text. Needed for the mobile app's
Mushaf reader; voice_search.py and recitation.py already consume this same
corpus but only for search/check, not for browsing it directly.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.quran_corpus_service import QuranCorpusService

router = APIRouter()

_corpus_service = QuranCorpusService()


class SurahSummary(BaseModel):
    surah_number: int
    surah_name_ar: str
    surah_name_en: str
    surah_name_translation_en: str
    revelation_type: str
    ayah_count: int


class Ayah(BaseModel):
    surah_number: int
    ayah_number: int
    global_ayah_number: int
    juz: int
    page: int
    text_uthmani: str
    text_simple: str
    basmalah: Optional[str]
    translation_en: str
    key: str


class SurahDetail(BaseModel):
    surah_number: int
    surah_name_ar: str
    surah_name_en: str
    surah_name_translation_en: str
    revelation_type: str
    ayahs: List[Ayah]


@router.get("/surahs", response_model=List[SurahSummary])
async def list_surahs():
    """All 114 surahs with their metadata and ayah counts."""
    ayahs = _corpus_service.load_or_fetch()

    summaries: dict = {}
    for ayah in ayahs:
        surah_number = ayah["surah_number"]
        if surah_number not in summaries:
            summaries[surah_number] = SurahSummary(
                surah_number=surah_number,
                surah_name_ar=ayah["surah_name_ar"],
                surah_name_en=ayah["surah_name_en"],
                surah_name_translation_en=ayah["surah_name_translation_en"],
                revelation_type=ayah["revelation_type"],
                ayah_count=0,
            )
        summaries[surah_number].ayah_count += 1

    return [summaries[n] for n in sorted(summaries)]


@router.get("/{surah}", response_model=SurahDetail)
async def get_surah(surah: int):
    """Full ayah list for one surah, all scripts + translation."""
    ayahs = _corpus_service.load_or_fetch()

    surah_ayahs = [a for a in ayahs if a["surah_number"] == surah]
    if not surah_ayahs:
        raise HTTPException(status_code=404, detail=f"Surah {surah} not found")

    surah_ayahs.sort(key=lambda a: a["ayah_number"])
    first = surah_ayahs[0]

    return SurahDetail(
        surah_number=surah,
        surah_name_ar=first["surah_name_ar"],
        surah_name_en=first["surah_name_en"],
        surah_name_translation_en=first["surah_name_translation_en"],
        revelation_type=first["revelation_type"],
        ayahs=[Ayah(**a) for a in surah_ayahs],
    )
