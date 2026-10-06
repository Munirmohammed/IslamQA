"""
Tafsir Endpoints
Quranic exegesis (Ibn Kathir Abridged, English) lookup and free-text
search -- the "ask a question about the Quran, get the relevant scholarly
commentary" companion experience. Public: reference content, not personal
state (same reasoning as tajweed/voice-search).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.config import settings
from app.core.dependencies import get_tafsir_search_service
from app.services.tafsir_search_service import TafsirSearchService
from app.services.tafsir_service import tafsir_service

router = APIRouter()


class TafsirAyahResponse(BaseModel):
    surah: int
    ayah: int
    ayah_from: int
    ayah_to: int
    text_html: str
    text_plain: str


class TafsirSearchResult(BaseModel):
    surah_number: int
    ayah_from: int
    ayah_to: int
    text_html: str
    text_plain: str
    fused_score: float


class TafsirSearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[TafsirSearchResult]


@router.get("/search", response_model=TafsirSearchResponse)
async def search_tafsir(
    q: str = Query(..., min_length=2, max_length=500, description="Free-text question"),
    limit: int = Query(default=5, ge=1, le=20),
    tafsir_search_service: TafsirSearchService = Depends(get_tafsir_search_service),
):
    """Free-text search over the tafsir corpus."""
    if not settings.ENABLE_TAFSIR:
        raise HTTPException(status_code=503, detail="Tafsir lookup is currently disabled")

    results = await tafsir_search_service.search(query=q, top_k=limit)
    return TafsirSearchResponse(
        query=results["query"],
        total_results=results["total_results"],
        results=[TafsirSearchResult(**r) for r in results["results"]],
    )


@router.get("/{surah}/{ayah}", response_model=TafsirAyahResponse)
async def get_ayah_tafsir(surah: int, ayah: int):
    """That ayah's tafsir block (may cover a range of ayahs it shares
    commentary with)."""
    if not settings.ENABLE_TAFSIR:
        raise HTTPException(status_code=503, detail="Tafsir lookup is currently disabled")

    # Cheap once cached on disk (the app startup lifespan already fetched
    # it, via TafsirSearchService's own TafsirService instance -- this is a
    # separate instance, same pattern as recitation.py's per-request
    # QuranCorpusService().load_or_fetch() call); only hits the network if
    # the shared cache file is somehow missing.
    tafsir_service.load_or_fetch()

    block = tafsir_service.get_ayah_tafsir(surah, ayah)
    if not block:
        raise HTTPException(status_code=404, detail=f"No tafsir found for ayah {surah}:{ayah}")

    return TafsirAyahResponse(
        surah=surah,
        ayah=ayah,
        ayah_from=block["ayah_from"],
        ayah_to=block["ayah_to"],
        text_html=block["text_html"],
        text_plain=block["text_plain"],
    )
